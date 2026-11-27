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


@pytest.fixture
async def store():
    return await make_store()


@pytest.mark.anyio
async def test_conversations_are_listed_per_person_newest_first(store):
    await store.save_turn("c1", "fake", None, "where is the canary runbook?", "here [a1b2c3]", [], user_id="maria")
    await store.save_turn("c2", "fake", None, "who owns billing?", "grace", [], user_id="maria")
    await store.save_turn("c3", "fake", None, "unrelated", "x", [], user_id="vivek")
    await store.save_turn("c1", "fake", None, "and the rollback?", "pin it", [], user_id="maria")
    rows = await store.list_for("maria")
    assert [r["id"] for r in rows] == ["c1", "c2"]
    assert rows[0]["title"] == "where is the canary runbook?"


@pytest.mark.anyio
async def test_get_returns_messages_and_owner(store):
    await store.save_turn("c1", "fake", None, "q", "a", [{"ref": "a1b2c3"}], user_id="maria")
    c = await store.get("c1")
    assert c["user_id"] == "maria" and [m["role"] for m in c["messages"]] == ["user", "assistant"]
    assert await store.get("nope") is None


@pytest.mark.anyio
async def test_a_session_from_another_runtime_is_not_resumed(store):
    await store.save_turn("c1", "codex", "thread-1", "q", "a", [])
    assert await store.runtime_session("c1", "api") is None and await store.runtime_session("c1", "codex") == "thread-1"
    await store.save_turn("c1", "api", "api-1", "q2", "a2", [])
    assert await store.runtime_session("c1", "api") == "api-1"
