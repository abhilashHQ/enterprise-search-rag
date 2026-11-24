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
