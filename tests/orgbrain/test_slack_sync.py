import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.db import Base, ConversationStore
from orgbrain.slack.sync import first_time


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def sessions():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationStore(engine).sessions


@pytest.mark.anyio
async def test_first_time_only_once():
    sm = await sessions()
    assert await first_time(sm, "Ev1") is True
    assert await first_time(sm, "Ev1") is False and await first_time(sm, "Ev2") is True


@pytest.mark.anyio
async def test_messages_accumulate_into_one_thread_document():
    from sqlalchemy import select

    from orgbrain.db import ConnectorSource, Outbox
    from orgbrain.slack.sync import index_message, thread_doc_id

    sm = await sessions()
    async with sm.begin() as s:
        s.add(ConnectorSource(id="slack", kind="slack", config={}))
    await index_message(sm, "C1", "eng-runtime", "1.0", "Maya Patel", "p99 is up 3x since the driver rollout")
    await index_message(sm, "C1", "eng-runtime", "1.0", "Kevin Wu", "rolling back the driver now")
    async with sm() as s:
        rows = (await s.execute(select(Outbox).order_by(Outbox.id))).scalars().all()
    assert [r.doc_id for r in rows] == [thread_doc_id("C1", "1.0")] * 2
    assert rows[-1].payload == {"source": "slack", "title": "eng-runtime",
                                "content": "Maya Patel: p99 is up 3x since the driver rollout\nKevin Wu: rolling back the driver now"}


class BackfillClient:
    async def auth_test(self):
        return {"user_id": "UBOT"}

    async def conversations_list(self, **kw):
        return {"channels": [{"id": "C1", "name": "support", "is_member": True},
                             {"id": "C2", "name": "random", "is_member": False}], "response_metadata": {}}

    async def conversations_history(self, channel, **kw):
        return {"messages": [
            {"ts": "2.0", "user": "U1", "text": "acme renewal moved to Thursday", "client_msg_id": "m2"},
            {"ts": "1.0", "user": "U2", "text": "who owns acme?", "client_msg_id": "m1", "reply_count": 1},
            {"ts": "1.5", "bot_id": "B1", "subtype": "bot_message", "text": "seeded"},
            {"ts": "3.0", "user": "U2", "text": "<@UBOT> when is the call?", "client_msg_id": "m3"}],
            "response_metadata": {}}

    async def conversations_replies(self, channel, ts, **kw):
        return {"messages": [{"ts": "1.0", "user": "U2", "text": "who owns acme?", "client_msg_id": "m1"},
                             {"ts": "1.1", "user": "U1", "text": "Kevin does", "client_msg_id": "m4", "thread_ts": "1.0"}],
                "response_metadata": {}}

    async def users_info(self, user):
        return {"user": {"real_name": {"U1": "Kevin Wu", "U2": "Maya Patel"}[user]}}


@pytest.mark.anyio
async def test_backfill_indexes_human_messages_once():
    from sqlalchemy import select

    from orgbrain.db import Outbox
    from orgbrain.slack.sync import backfill, thread_doc_id

    sm = await sessions()
    assert await backfill(BackfillClient(), sm, pause=0) == 3
    assert await backfill(BackfillClient(), sm, pause=0) == 0
    async with sm() as s:
        rows = (await s.execute(select(Outbox).order_by(Outbox.id))).scalars().all()
    latest = {r.doc_id: r.payload["content"] for r in rows}
    assert latest == {thread_doc_id("C1", "1.0"): "Maya Patel: who owns acme?\nKevin Wu: Kevin does",
                      thread_doc_id("C1", "2.0"): "Kevin Wu: acme renewal moved to Thursday"}
