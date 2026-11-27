"""Files uploaded from the Sources page land in one managed folder, synced through the folder connector."""

import asyncio
from pathlib import Path, PurePath

from sqlalchemy import func, select

from orgbrain.connectors.folder import SUFFIXES
from orgbrain.db import ConnectorSource, Outbox, SourceFile


def save_uploads(root: Path, files: list[tuple[str, bytes]]) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    saved, rejected = [], []
    for name, data in files:
        base = PurePath(name.replace("\\", "/")).name
        if not base or base.startswith(".") or PurePath(base).suffix.lower() not in SUFFIXES:
            rejected.append(name)
            continue
        (root / base).write_bytes(data)
        saved.append(base)
    if not saved:
        raise ValueError(f"no supported files: {', '.join(rejected)}")
    return saved


async def sources_overview(sessions, docs) -> dict:
    async with sessions() as s:
        connectors = (await s.execute(select(ConnectorSource).order_by(ConnectorSource.id))).scalars().all()
        files = {}
        for c in connectors:
            files[c.id] = list((await s.execute(select(SourceFile.doc_id).where(SourceFile.source_id == c.id))).scalars())
        pending = (await s.execute(select(func.count()).select_from(Outbox).where(Outbox.published_at.is_(None)))).scalar_one()
    corpus = await asyncio.to_thread(docs.counts) if docs is not None else {}
    indexed = {cid: len(await asyncio.to_thread(docs.has, ids)) if docs is not None else 0 for cid, ids in files.items()}
    return {"corpus": corpus, "pending": pending, "connectors": [
        {"id": c.id, "kind": c.kind, "path": (c.config or {}).get("path"),
         "last_synced_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
         "files": len(files[c.id]), "indexed": indexed[c.id]} for c in connectors]}
