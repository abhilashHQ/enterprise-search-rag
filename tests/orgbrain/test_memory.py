import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.db import Base, ConversationStore, Outbox, Person
from orgbrain.memory import MemoryStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def store():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = ConversationStore(engine).sessions
    async with sm.begin() as s:
        s.add_all([Person(id="maria", name="Maria Lopez", is_admin=True), Person(id="sam", name="Sam Ortiz")])
    return MemoryStore(sm), sm


@pytest.mark.anyio
async def test_only_admins_decide_and_approval_indexes_the_memory():
    mem, sm = await store()
    mid = await mem.propose("Deploy freeze starts Dec 15", proposed_by="sam", conversation_id="c1")
    assert [m["status"] for m in await mem.list("pending")] == ["pending"]
    with pytest.raises(PermissionError):
        await mem.decide(mid, "approve", "sam")
    out = await mem.decide(mid, "approve", "maria")
    assert out["status"] == "approved" and out["decided_by"] == "maria"
    with pytest.raises(ValueError):
        await mem.decide(mid, "reject", "maria")
    await mem.decide(mid, "forget", "maria")
    async with sm() as s:
        rows = [(o.kind, o.doc_id, o.payload) for o in (await s.execute(select(Outbox).order_by(Outbox.id))).scalars()]
    assert rows[0][:2] == ("upsert", f"memory:{mid}") and rows[0][2]["source"] == "memory"
    assert rows[0][2]["content"].startswith("Deploy freeze starts Dec 15\n\nProposed by Sam Ortiz, approved by Maria Lopez")
    assert rows[1] == ("delete", f"memory:{mid}", {})


@pytest.mark.anyio
async def test_unknown_memory_and_rejection():
    mem, _ = await store()
    with pytest.raises(LookupError):
        await mem.decide(99, "approve", "maria")
    mid = await mem.propose("Use pnpm")
    assert (await mem.decide(mid, "reject", "maria"))["status"] == "rejected"
