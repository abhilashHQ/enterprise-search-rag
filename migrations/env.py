import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from orgbrain.config import Settings
from orgbrain.db import Base

URL = context.config.get_main_option("sqlalchemy.url") or Settings.from_env().database_url
target_metadata = Base.metadata


def run_offline() -> None:
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run(conn) -> None:
    context.configure(connection=conn, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        await conn.run_sync(do_run)
    await engine.dispose()


run_offline() if context.is_offline_mode() else asyncio.run(run_online())
