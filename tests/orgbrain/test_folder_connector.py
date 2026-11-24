from pathlib import PurePosixPath

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.connectors.folder import source_for, sync_folder
from orgbrain.db import Base, ConnectorSource, ConversationStore, Outbox


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def sessions():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = ConversationStore(engine).sessions
    async with sm.begin() as s:
        s.add(ConnectorSource(id="notes", kind="folder", config={}))
    return sm


def test_source_comes_from_a_known_top_folder():
    assert source_for(PurePosixPath("confluence/runbook.md")) == "confluence"
    assert source_for(PurePosixPath("memory/x.md")) == "files"
    assert source_for(PurePosixPath("misc/x.md")) == "files" and source_for(PurePosixPath("x.md")) == "files"


@pytest.mark.anyio
async def test_sync_enqueues_adds_changes_and_deletes(tmp_path):
    sm = await sessions()
    (tmp_path / "jira").mkdir()
    (tmp_path / "jira" / "INC-1.md").write_text("Root cause: expired cert.", encoding="utf8")
    (tmp_path / "plan.txt").write_text("Q1 plan", encoding="utf8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    r = await sync_folder(sm, "notes", tmp_path)
    assert (r.added, r.updated, r.deleted) == (2, 0, 0) and r.skipped == ["image.png"]
    assert (await sync_folder(sm, "notes", tmp_path)).added == 0

    (tmp_path / "plan.txt").write_text("Q1 plan, revised", encoding="utf8")
    (tmp_path / "jira" / "INC-1.md").unlink()
    r = await sync_folder(sm, "notes", tmp_path)
    assert (r.added, r.updated, r.deleted) == (0, 1, 1)
    async with sm() as s:
        rows = [(o.kind, o.doc_id, o.payload.get("source")) for o in (await s.execute(select(Outbox).order_by(Outbox.id))).scalars()]
    assert rows == [("upsert", "file:notes:jira/INC-1.md", "jira"), ("upsert", "file:notes:plan.txt", "files"),
                    ("upsert", "file:notes:plan.txt", "files"), ("delete", "file:notes:jira/INC-1.md", None)]
