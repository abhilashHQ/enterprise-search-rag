import fakeredis
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.db import Base, ConversationStore, Outbox, enqueue
from orgbrain.worker import consume_once, ensure_group, relay_once


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeWriter:
    def __init__(self):
        self.calls = []

    def upsert(self, doc):
        self.calls.append(("upsert", doc.doc_id, doc.source, doc.title, doc.content))
        return [1.0, 0.0]

    def delete(self, doc_id):
        self.calls.append(("delete", doc_id))
        return None


async def sessions():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationStore(engine).sessions


@pytest.mark.anyio
async def test_outbox_rows_reach_the_writer_once_and_in_order():
    sm, redis, writer, seen = await sessions(), fakeredis.aioredis.FakeRedis(decode_responses=True), FakeWriter(), []
    async with sm.begin() as s:
        enqueue(s, "upsert", "memory:1", {"source": "memory", "title": "Freeze", "content": "Dec 15"})
        enqueue(s, "delete", "file:n:a.md")

    async def on_indexed(doc_id, vec):
        seen.append((doc_id, vec))

    await ensure_group(redis)
    await ensure_group(redis)
    assert await relay_once(sm, redis) == 2 and await relay_once(sm, redis) == 0
    assert await consume_once(redis, writer, on_indexed, block_ms=10) == 2
    assert await consume_once(redis, writer, on_indexed, block_ms=10) == 0
    assert writer.calls == [("upsert", "memory:1", "memory", "Freeze", "Dec 15"), ("delete", "file:n:a.md")]
    assert seen == [("memory:1", [1.0, 0.0]), ("file:n:a.md", None)]
    async with sm() as s:
        assert all(r.published_at is not None for r in (await s.execute(select(Outbox))).scalars())


@pytest.mark.anyio
async def test_unacked_entries_are_redelivered_to_the_same_consumer():
    sm, redis = await sessions(), fakeredis.aioredis.FakeRedis(decode_responses=True)
    async with sm.begin() as s:
        enqueue(s, "upsert", "memory:2", {"source": "memory", "title": "t", "content": "c"})
    await ensure_group(redis)
    await relay_once(sm, redis)

    class Boom(FakeWriter):
        def upsert(self, doc):
            raise RuntimeError("model service down")

    with pytest.raises(RuntimeError):
        await consume_once(redis, Boom(), block_ms=10)
    ok = FakeWriter()
    assert await consume_once(redis, ok, block_ms=10) == 1 and ok.calls[0][1] == "memory:2"
