import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.db import Base, ConversationStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def make_store():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationStore(engine)


@pytest.mark.anyio
async def test_turns_persist_and_resume_id_updates():
    store = await make_store()
    assert await store.runtime_session("c1") is None
    cites = [{"ref": "a1b2c3", "doc_id": "d1", "source": "confluence", "title": "Runbook"}]
    await store.save_turn("c1", "codex", "thread-1", "how?", "Like this [a1b2c3].", cites)
    await store.save_turn("c1", "codex", "thread-1", "and staging?", "Same.", [])
    assert await store.runtime_session("c1") == "thread-1"
    msgs = await store.messages("c1")
    assert [(m["role"], m["text"]) for m in msgs] == [("user", "how?"), ("assistant", "Like this [a1b2c3]."),
                                                      ("user", "and staging?"), ("assistant", "Same.")]
    assert msgs[1]["citations"] == cites


@pytest.mark.anyio
async def test_missing_session_id_keeps_the_old_one():
    store = await make_store()
    await store.save_turn("c2", "api", "s-1", "q", "a", [])
    await store.save_turn("c2", "api", None, "q2", "a2", [])
    assert await store.runtime_session("c2") == "s-1"


from sqlalchemy import select

from orgbrain.db import Memory, Outbox, enqueue


@pytest.mark.anyio
async def test_enqueue_commits_with_the_callers_row():
    store = await make_store()
    async with store.sessions.begin() as s:
        m = Memory(text="Deploy freeze starts Dec 15", proposed_by="maria.lopez")
        s.add(m)
        await s.flush()
        enqueue(s, "upsert", f"memory:{m.id}", {"source": "memory", "title": "t", "content": m.text})
    async with store.sessions() as s:
        row = (await s.execute(select(Outbox))).scalar_one()
        mem = (await s.execute(select(Memory))).scalar_one()
    assert (row.kind, row.doc_id, row.published_at) == ("upsert", f"memory:{mem.id}", None)
    assert mem.status == "pending" and row.payload["content"] == "Deploy freeze starts Dec 15"
