"""Ingest worker: relays outbox rows to a Redis stream and indexes each event with IndexWriter.

  uv run --extra app orgbrain-worker          # needs Postgres, Redis, Qdrant and orgbrain-models running
"""

import argparse
import asyncio
import json
import logging
import sys

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import func, select

from orgbrain.db import Outbox
from orgbrain.index_writer import IndexWriter, NewDoc

STREAM, GROUP = "orgbrain:ingest", "workers"
log = logging.getLogger("orgbrain.worker")


async def relay_once(sessions, redis: Redis, batch: int = 100) -> int:
    async with sessions.begin() as s:
        rows = (await s.execute(select(Outbox).where(Outbox.published_at.is_(None)).order_by(Outbox.id).limit(batch))).scalars().all()
        for r in rows:
            await redis.xadd(STREAM, {"outbox_id": r.id, "kind": r.kind, "doc_id": r.doc_id, "payload": json.dumps(r.payload)})
            r.published_at = func.now()
    return len(rows)


async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def _apply(writer: IndexWriter, fields: dict) -> list[float] | None:
    if fields["kind"] == "delete":
        return writer.delete(fields["doc_id"])
    p = json.loads(fields["payload"])
    return writer.upsert(NewDoc(fields["doc_id"], p["source"], p["title"], p["content"]))


async def consume_once(redis: Redis, writer, on_indexed=None, consumer: str = "worker-1", block_ms: int = 5000) -> int:
    done = 0
    for start, block in (("0", None), (">", block_ms)):
        resp = await redis.xreadgroup(GROUP, consumer, {STREAM: start}, count=10, block=block)
        for _, entries in resp or []:
            for entry_id, fields in entries:
                vec = await asyncio.to_thread(_apply, writer, fields)
                if on_indexed:
                    await on_indexed(fields["doc_id"], vec)
                await redis.xack(STREAM, GROUP, entry_id)
                done += 1
        if done:
            return done
    return done


async def run(settings, consumer: str) -> None:
    from qdrant_client import QdrantClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from orgbrain.cache import SemanticCache
    from orgbrain.index_redwood import read_bm25_stats
    from orgbrain.models_client import ModelsClient
    from orgbrain.waiting import wait_for

    sessions = async_sessionmaker(create_async_engine(settings.database_url), expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=30)
    models_ = ModelsClient(settings.models_url)
    wait_for(models_.health, "model service")
    writer = IndexWriter(QdrantClient(url=settings.qdrant_url, timeout=120), models_,
                         read_bm25_stats(settings.bm25_stats_path)["avgdl"], settings.live_path)
    cache = SemanticCache(Redis.from_url(settings.redis_url))

    async def on_indexed(doc_id, vec):
        if vec is not None:
            log.info("%s indexed, %d cached answers dropped", doc_id, await cache.invalidate(vec))

    await ensure_group(redis)

    async def relay():
        while True:
            if not await relay_once(sessions, redis):
                await asyncio.sleep(1)

    async def consume():
        while True:
            await consume_once(redis, writer, on_indexed, consumer)

    await asyncio.gather(relay(), consume())


def main() -> None:
    from orgbrain.config import Settings

    p = argparse.ArgumentParser(prog="orgbrain-worker", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--consumer", default="worker-1")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(message)s")
    asyncio.run(run(Settings.from_env(), a.consumer))


if __name__ == "__main__":
    main()
