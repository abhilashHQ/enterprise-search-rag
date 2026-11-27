"""orgbrain command line.

  orgbrain demo                                   # download the prebuilt Redwood index and load it (about 10 GB)
  orgbrain connect folder C:/notes --name notes   # index a folder; --watch 10 keeps syncing
  orgbrain status                                 # one line per service, exit 1 if anything is down
"""

import argparse
import asyncio
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from entsearch.data import ROOT
from orgbrain.config import Settings
from orgbrain.connectors.folder import run as folder_run
from orgbrain.demo_index import DEFAULT_REPO

COLLECTIONS = ("documents", "chunks")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orgbrain", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="download and load the prebuilt Redwood index")
    d.add_argument("--repo", default=DEFAULT_REPO, help="Hugging Face dataset repo")
    d.add_argument("--revision", help="a branch, tag or commit of the dataset repo")
    d.add_argument("--dir", type=Path, default=ROOT / "data/demo", help="where the download goes")
    d.add_argument("--force", action="store_true", help="replace an index that's already loaded")
    d.add_argument("--keep-download", action="store_true", help="keep the downloaded files afterwards")
    c = sub.add_parser("connect", help="add a source")
    kinds = c.add_subparsers(dest="kind", required=True)
    f = kinds.add_parser("folder")
    f.add_argument("path", type=Path)
    f.add_argument("--name", required=True, help="source id, e.g. notes")
    f.add_argument("--watch", type=float, help="seconds between syncs; omit for one sync")
    sub.add_parser("status", help="health of every service")
    return p


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")


def demo(a, settings: Settings) -> int:
    from orgbrain import demo_index

    print(f"downloading {a.repo} into {a.dir}", flush=True)
    m = demo_index.download(a.repo, a.dir, a.revision)
    total = sum(x.size for x in m.artifacts) / demo_index.GB
    print(f"verified {len(m.artifacts)} files, {total:.1f} GB", flush=True)
    migrate()
    asyncio.run(demo_index.restore(m, a.dir, settings, force=a.force))
    if not a.keep_download:
        shutil.rmtree(a.dir)
    print("the redwood demo is loaded. open http://localhost:3000 and sign in as anyone.")
    return 0


def probes(settings: Settings) -> dict[str, Callable[[], Awaitable[str]]]:
    async def get(url: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=10) as http:
            return await http.get(url)

    async def qdrant() -> str:
        counts = []
        for c in COLLECTIONS:
            r = await get(f"{settings.qdrant_url}/collections/{c}")
            counts.append(f"{c} {r.json()['result']['points_count']:,}" if r.status_code == 200 else f"{c} missing")
        return ", ".join(counts)

    async def postgres() -> str:
        from sqlalchemy import func, select
        from sqlalchemy.ext.asyncio import create_async_engine

        from orgbrain.db import Outbox, Person

        engine = create_async_engine(settings.database_url)
        try:
            async with engine.connect() as conn:
                people = (await conn.execute(select(func.count()).select_from(Person))).scalar_one()
                pending = (await conn.execute(
                    select(func.count()).select_from(Outbox).where(Outbox.published_at.is_(None)))).scalar_one()
        finally:
            await engine.dispose()
        return f"{people:,} people, {pending:,} outbox rows pending"

    async def redis() -> str:
        from redis.asyncio import Redis

        r = Redis.from_url(settings.redis_url)
        try:
            await r.ping()
        finally:
            await r.aclose()
        return "ping ok"

    async def http_ok(url: str) -> str:
        r = await get(url)
        r.raise_for_status()
        return r.text[:80]

    async def search() -> str:
        r = await get(settings.mcp_url)
        if r.status_code >= 500:
            raise ConnectionError(f"HTTP {r.status_code}")
        return f"listening at {settings.mcp_url}"

    return {"qdrant": qdrant, "postgres": postgres, "redis": redis,
            "models": lambda: http_ok(f"{settings.models_url}/health"), "search": search,
            "api": lambda: http_ok(f"{settings.api_url}/api/health")}


async def _status(settings: Settings) -> int:
    down = 0
    for name, probe in probes(settings).items():
        try:
            detail = await probe()
            print(f"up    {name:<9} {detail}")
        except Exception as e:
            down += 1
            print(f"down  {name:<9} {type(e).__name__}: {e}")
    return 1 if down else 0


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings.from_env()
    if a.cmd == "demo":
        return demo(a, settings)
    if a.cmd == "connect":
        asyncio.run(folder_run(settings.database_url, a.path, a.name, a.watch))
        return 0
    return asyncio.run(_status(settings))
