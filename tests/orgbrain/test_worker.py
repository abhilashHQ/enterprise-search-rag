import json
import sqlite3

import fakeredis
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.db import Base, ConversationStore, Outbox, enqueue
from orgbrain.worker import (ATTEMPTS, DEAD, GROUP, STREAM, consume_once, ensure_group, forever, is_transient,
                             relay_once)


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
async def test_transient_failure_leaves_the_entry_pending_without_counting_it():
    sm, redis = await sessions(), fakeredis.aioredis.FakeRedis(decode_responses=True)
    async with sm.begin() as s:
        enqueue(s, "upsert", "memory:2", {"source": "memory", "title": "t", "content": "c"})
    await ensure_group(redis)
    await relay_once(sm, redis)

    class Down(FakeWriter):
        def upsert(self, doc):
            raise httpx.ConnectError("model service down")

    for _ in range(5):
        with pytest.raises(httpx.ConnectError):
            await consume_once(redis, Down(), block_ms=10)
    assert await redis.hlen(ATTEMPTS) == 0 and await redis.xlen(DEAD) == 0
    ok = FakeWriter()
    assert await consume_once(redis, ok, block_ms=10) == 1 and ok.calls[0][1] == "memory:2"


@pytest.mark.anyio
async def test_a_bad_event_is_dead_lettered_after_three_attempts_and_the_next_one_still_indexes():
    redis, writer = fakeredis.aioredis.FakeRedis(decode_responses=True), FakeWriter()
    await ensure_group(redis)
    await redis.xadd(STREAM, {"outbox_id": "1", "kind": "upsert", "doc_id": "memory:9", "payload": "{not json"})
    await redis.xadd(STREAM, {"outbox_id": "2", "kind": "upsert", "doc_id": "memory:10",
                              "payload": json.dumps({"source": "memory", "title": "t", "content": "c"})})
    assert [await consume_once(redis, writer, block_ms=10) for _ in range(2)] == [0, 0] and writer.calls == []
    assert await consume_once(redis, writer, block_ms=10) == 2 and [c[1] for c in writer.calls] == ["memory:10"]
    dead = await redis.xrange(DEAD)
    assert len(dead) == 1 and dead[0][1]["doc_id"] == "memory:9" and "JSONDecodeError" in dead[0][1]["error"]
    assert await consume_once(redis, writer, block_ms=10) == 0
    assert await redis.hlen(ATTEMPTS) == 0 and (await redis.xpending(STREAM, GROUP))["pending"] == 0


def test_transient_errors_are_connection_level():
    assert is_transient(httpx.ConnectError("refused")) and is_transient(ConnectionRefusedError())
    assert is_transient(httpx.HTTPStatusError("503", request=httpx.Request("POST", "http://m"),
                                              response=httpx.Response(503)))
    assert is_transient(sqlite3.OperationalError("database is locked"))
    assert not is_transient(httpx.HTTPStatusError("422", request=httpx.Request("POST", "http://m"),
                                                  response=httpx.Response(422)))
    assert not is_transient(KeyError("kind")) and not is_transient(ValueError("bad"))


class Stop(BaseException):
    pass


@pytest.mark.anyio
async def test_forever_backs_off_on_failures_and_resets_after_a_success():
    outcomes, slept = iter([httpx.ConnectError("down"), KeyError("bad"), None, httpx.ConnectError("down"), Stop()]), []

    async def step():
        if (o := next(outcomes)) is not None:
            raise o

    async def sleep(s):
        slept.append(s)

    with pytest.raises(Stop):
        await forever(step, "ingest", sleep=sleep)
    assert slept == [2.0, 4.0, 2.0]
