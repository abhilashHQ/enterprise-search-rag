import json
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
import zstandard
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain import demo_index
from orgbrain.config import Settings
from orgbrain.db import Base, ConversationStore
from orgbrain.demo_index import MANIFEST, Artifact, Manifest, read_manifest, sha256_file, write_manifest
from orgbrain.people import PeopleStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _artifact(path: Path, target: str) -> Artifact:
    return Artifact(path.name, sha256_file(path), path.stat().st_size, target)


def _manifest(artifacts: list[Artifact]) -> Manifest:
    return Manifest(1, "redwood", "Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B", "2026-11-27", artifacts)


def _sqlite(path: Path, rows: list[tuple[str, str]]) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE docs (doc_id TEXT PRIMARY KEY, content TEXT)")
    con.executemany("INSERT INTO docs VALUES (?, ?)", rows)
    con.commit()
    con.close()


def _zst(src: Path, dest: Path) -> None:
    with open(src, "rb") as fin, open(dest, "wb") as fout:
        zstandard.ZstdCompressor().copy_stream(fin, fout)


@pytest.fixture
def build(tmp_path):
    """A complete artifact set like the published one, small."""
    out = tmp_path / "build"
    out.mkdir()
    (out / "qdrant-documents.snapshot").write_bytes(b"documents snapshot")
    (out / "qdrant-chunks.snapshot").write_bytes(b"chunks snapshot")
    _sqlite(tmp_path / "docstore.sqlite", [("d1", "hello"), ("d2", "world")])
    _zst(tmp_path / "docstore.sqlite", out / "docstore.sqlite.zst")
    _sqlite(tmp_path / "fts.sqlite", [("d1", "x")])
    _zst(tmp_path / "fts.sqlite", out / "fts.sqlite.zst")
    (out / "bm25.json").write_text(json.dumps({"avgdl": 12.5}))
    people = [
        {"id": "monica.patel", "name": "Monica Patel", "email": "monica.patel@redwoodinference.com", "role": "VP Eng",
         "team": "Engineering", "aliases": [], "topics": ["canary"], "sources": {"slack": 3}, "doc_count": 3},
        {"id": "vivek.kulkarni", "name": "Vivek Kulkarni", "email": None, "role": "SRE", "team": "Infra",
         "aliases": [], "topics": [], "sources": {}, "doc_count": 1},
        {"id": "ana.ruiz", "name": "Ana Ruiz", "email": None, "role": None, "team": None,
         "aliases": [], "topics": [], "sources": {}, "doc_count": 0},
    ]
    (out / "people.jsonl").write_text("".join(json.dumps(p) + "\n" for p in people))
    targets = {"qdrant-documents.snapshot": "qdrant:documents", "qdrant-chunks.snapshot": "qdrant:chunks",
               "docstore.sqlite.zst": "data/index/docstore.sqlite", "fts.sqlite.zst": "data/index/fts.sqlite",
               "bm25.json": "data/index/bm25.json", "people.jsonl": "postgres:people"}
    write_manifest(_manifest([_artifact(out / n, t) for n, t in targets.items()]), out / MANIFEST)
    return out


def test_manifest_round_trip(tmp_path):
    m = _manifest([Artifact("bm25.json", "ab" * 32, 10, "data/index/bm25.json")])
    write_manifest(m, tmp_path / MANIFEST)
    assert read_manifest(tmp_path / MANIFEST) == m


def test_sha256_file(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    assert sha256_file(p, chunk=2) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _fake_snapshot_download(src: Path, calls: list):
    def fake(repo_id, repo_type, local_dir, revision=None):
        calls.append((repo_id, repo_type, revision))
        shutil.copytree(src, local_dir, dirs_exist_ok=True)
        return str(local_dir)
    return fake


def test_download_verifies_every_artifact(build, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(demo_index, "snapshot_download", _fake_snapshot_download(build, calls))
    m = demo_index.download("me/orgbrain-redwood-index", tmp_path / "dl", revision="v1")
    assert calls == [("me/orgbrain-redwood-index", "dataset", "v1")]
    assert len(m.artifacts) == 6


def test_download_names_the_corrupted_file(build, tmp_path, monkeypatch):
    (build / "bm25.json").write_text(json.dumps({"avgdl": 99.0}))
    monkeypatch.setattr(demo_index, "snapshot_download", _fake_snapshot_download(build, []))
    with pytest.raises(ValueError, match="bm25.json"):
        demo_index.download("me/x", tmp_path / "dl")


def _settings(tmp_path: Path) -> Settings:
    index = tmp_path / "data/index"
    return replace(Settings(), qdrant_url="http://qdrant.test", docstore_path=index / "docstore.sqlite",
                   fts_path=index / "fts.sqlite", bm25_stats_path=index / "bm25.json",
                   live_path=tmp_path / "data/orgbrain/live.sqlite")


@pytest.fixture
async def people_store():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return PeopleStore(ConversationStore(engine).sessions)


@pytest.fixture
def fake_qdrant(monkeypatch):
    state = {"points": {}, "uploads": []}

    def upload(url, collection, path):
        state["uploads"].append((url, collection, Path(path).read_bytes()))

    monkeypatch.setattr(demo_index, "upload_snapshot", upload)
    monkeypatch.setattr(demo_index, "collection_points", lambda url, c: state["points"].get(c))
    return state


@pytest.mark.anyio
async def test_restore_loads_everything(build, tmp_path, fake_qdrant, people_store):
    settings = _settings(tmp_path)
    await demo_index.restore(read_manifest(build / MANIFEST), build, settings, people=people_store)

    assert sorted((c, b) for _, c, b in fake_qdrant["uploads"]) == [
        ("chunks", b"chunks snapshot"), ("documents", b"documents snapshot")]
    assert all(u == "http://qdrant.test" for u, _, _ in fake_qdrant["uploads"])
    con = sqlite3.connect(settings.docstore_path)
    assert con.execute("SELECT doc_id, content FROM docs ORDER BY doc_id").fetchall() == [("d1", "hello"), ("d2", "world")]
    con.close()
    assert settings.fts_path.exists()
    assert json.loads(settings.bm25_stats_path.read_text()) == {"avgdl": 12.5}
    assert [p["id"] for p in await people_store.admins()] == ["monica.patel", "vivek.kulkarni"]
    assert (await people_store.get("ana.ruiz"))["is_admin"] is False
    assert settings.live_path.exists()


@pytest.mark.anyio
async def test_restore_refuses_existing_targets_without_force(build, tmp_path, fake_qdrant, people_store):
    settings = _settings(tmp_path)
    settings.docstore_path.parent.mkdir(parents=True)
    settings.docstore_path.write_bytes(b"keep me")
    with pytest.raises(FileExistsError, match="docstore.sqlite"):
        await demo_index.restore(read_manifest(build / MANIFEST), build, settings, people=people_store)
    assert settings.docstore_path.read_bytes() == b"keep me"
    assert fake_qdrant["uploads"] == []

    await demo_index.restore(read_manifest(build / MANIFEST), build, settings, people=people_store, force=True)
    assert settings.docstore_path.read_bytes() != b"keep me"


@pytest.mark.anyio
async def test_restore_refuses_a_collection_with_points_without_force(build, tmp_path, fake_qdrant, people_store):
    fake_qdrant["points"]["chunks"] = 42
    with pytest.raises(FileExistsError, match="chunks"):
        await demo_index.restore(read_manifest(build / MANIFEST), build, _settings(tmp_path), people=people_store)
    assert fake_qdrant["uploads"] == []
