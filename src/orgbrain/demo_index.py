"""The prebuilt Redwood index: a manifest of artifacts on a Hugging Face dataset repo, downloaded, verified and
restored into a running stack by `orgbrain demo`."""

import asyncio
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import zstandard
from huggingface_hub import snapshot_download

from orgbrain.config import Settings
from orgbrain.fts import ensure_live

MANIFEST = "manifest.json"
DEFAULT_REPO = "<filled in Task 3 once the user names the HF repo>"
ADMINS = ["monica.patel", "vivek.kulkarni"]
GB = 1 << 30


@dataclass(frozen=True)
class Artifact:
    name: str
    sha256: str
    size: int
    target: str


@dataclass(frozen=True)
class Manifest:
    version: int
    corpus: str
    embedder: str
    reranker: str
    created: str
    artifacts: list[Artifact]


def read_manifest(path: Path) -> Manifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(**{**raw, "artifacts": [Artifact(**a) for a in raw["artifacts"]]})


def write_manifest(m: Manifest, path: Path) -> None:
    path.write_text(json.dumps(asdict(m), indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def download(repo: str, dest: Path, revision: str | None = None) -> Manifest:
    snapshot_download(repo_id=repo, repo_type="dataset", local_dir=dest, revision=revision)
    m = read_manifest(dest / MANIFEST)
    for a in m.artifacts:
        path = dest / a.name
        if not path.exists() or path.stat().st_size != a.size or sha256_file(path) != a.sha256:
            raise ValueError(f"{a.name} failed verification (missing, wrong size or wrong sha256); "
                             f"delete {path} and run orgbrain demo again")
    return m


class _Progress:
    """A file object that prints how much of it has been read every 5%."""

    def __init__(self, path: Path, label: str):
        self.f = open(path, "rb")
        self.total = path.stat().st_size
        self.label = label
        self.done = 0
        self.step = 0

    def read(self, n: int = -1) -> bytes:
        block = self.f.read(n)
        self.done += len(block)
        if self.total and self.done * 20 // self.total > self.step:
            self.step = self.done * 20 // self.total
            print(f"  {self.label}: {self.done / GB:.2f} / {self.total / GB:.2f} GB", flush=True)
        return block

    def fileno(self) -> int:
        return self.f.fileno()

    def seek(self, *args) -> int:
        return self.f.seek(*args)

    def tell(self) -> int:
        return self.f.tell()

    def close(self) -> None:
        self.f.close()


def collection_points(qdrant_url: str, collection: str) -> int | None:
    r = httpx.get(f"{qdrant_url}/collections/{collection}", timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()["result"].get("points_count") or 0


def upload_snapshot(qdrant_url: str, collection: str, path: Path) -> None:
    """Qdrant runs in a container that can't see this machine's files, so the snapshot goes up over HTTP."""
    f = _Progress(path, f"qdrant {collection}")
    try:
        r = httpx.post(f"{qdrant_url}/collections/{collection}/snapshots/upload", params={"priority": "snapshot"},
                       files={"snapshot": (path.name, f, "application/octet-stream")}, timeout=None)
        r.raise_for_status()
    finally:
        f.close()


def _decompress(src: Path, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with open(src, "rb") as fin, open(tmp, "wb") as fout:
        zstandard.ZstdDecompressor().copy_stream(fin, fout, read_size=1 << 20, write_size=1 << 20)
    tmp.replace(dest)


def _local_target(target: str, settings: Settings) -> Path:
    paths = {"data/index/docstore.sqlite": settings.docstore_path, "data/index/fts.sqlite": settings.fts_path,
             "data/index/bm25.json": settings.bm25_stats_path}
    if target not in paths:
        raise ValueError(f"unknown artifact target {target!r}")
    return paths[target]


async def restore(m: Manifest, src: Path, settings: Settings, force: bool = False, people=None) -> None:
    qdrant = [(a, a.target.split(":", 1)[1]) for a in m.artifacts if a.target.startswith("qdrant:")]
    files = [(a, _local_target(a.target, settings)) for a in m.artifacts if a.target.startswith("data/")]
    people_art = [a for a in m.artifacts if a.target == "postgres:people"]

    if not force:
        for _, c in qdrant:
            if n := await asyncio.to_thread(collection_points, settings.qdrant_url, c):
                raise FileExistsError(f"qdrant collection {c} already has {n:,} points; pass --force to replace it")
        for _, dest in files:
            if dest.exists():
                raise FileExistsError(f"{dest} already exists; pass --force to replace it")

    for a, dest in files:
        print(f"writing {dest}", flush=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if a.name.endswith(".zst"):
            await asyncio.to_thread(_decompress, src / a.name, dest)
        else:
            shutil.copyfile(src / a.name, dest)
    if people_art:
        if people is None:
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            from orgbrain.people import PeopleStore

            people = PeopleStore(async_sessionmaker(create_async_engine(settings.database_url), expire_on_commit=False))
        rows = [json.loads(line) for line in (src / people_art[0].name).read_text(encoding="utf-8").splitlines() if line]
        await people.replace_all(rows)
        await people.set_admin(ADMINS, True)
        print(f"loaded {len(rows):,} people, admins {', '.join(ADMINS)}", flush=True)
    ensure_live(settings.live_path)
    # Last: the search service starts serving once both collections exist, and by then the files above are in place.
    for a, c in qdrant:
        print(f"restoring qdrant {c} from {a.name} ({a.size / GB:.2f} GB)", flush=True)
        await asyncio.to_thread(upload_snapshot, settings.qdrant_url, c, src / a.name)
