"""Folder connector: every .md, .txt, .pdf and .docx file under a directory becomes a document. A top-level subfolder
named after an app (confluence/, jira/, ...) tags its files with that source; everything else is `files`.

  uv run --extra app orgbrain-connect folder C:/path/to/notes --name notes            # one sync
  uv run --extra app orgbrain-connect folder C:/path/to/notes --name notes --watch 10 # keep syncing every 10 s
"""

import argparse
import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from sqlalchemy import func, select

from orgbrain.db import ConnectorSource, SourceFile, enqueue
from orgbrain.sources import Source

SUFFIXES = {".md", ".txt", ".pdf", ".docx"}
APP_SOURCES = {s.value for s in Source} - {Source.MEMORY.value, Source.FILES.value}
log = logging.getLogger("orgbrain.folder")


@dataclass
class SyncReport:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: list[str] = field(default_factory=list)


def source_for(rel: PurePosixPath) -> str:
    return rel.parts[0] if len(rel.parts) > 1 and rel.parts[0] in APP_SOURCES else Source.FILES.value


def parse(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf8", errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix == ".docx":
        from docx import Document

        return "\n".join(p.text for p in Document(path).paragraphs)
    raise ValueError(f"unsupported file type {suffix}")


async def sync_folder(sessions, source_id: str, root: Path) -> SyncReport:
    report, seen = SyncReport(), set()
    async with sessions() as s:
        known = {f.rel_path: f.sha256 for f in (await s.execute(select(SourceFile).where(SourceFile.source_id == source_id))).scalars()}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if path.suffix.lower() not in SUFFIXES:
            report.skipped.append(str(rel))
            continue
        seen.add(str(rel))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if known.get(str(rel)) == sha:
            continue
        try:
            content = parse(path)
        except Exception as e:
            log.warning("skipping %s: %s", rel, e)
            report.skipped.append(str(rel))
            continue
        doc_id = f"file:{source_id}:{rel}"
        async with sessions.begin() as s:
            await s.merge(SourceFile(source_id=source_id, rel_path=str(rel), doc_id=doc_id, sha256=sha))
            enqueue(s, "upsert", doc_id, {"source": source_for(rel), "title": rel.name, "content": content})
        if str(rel) in known:
            report.updated += 1
        else:
            report.added += 1
    for rel in known.keys() - seen:
        async with sessions.begin() as s:
            row = await s.get(SourceFile, (source_id, rel))
            enqueue(s, "delete", row.doc_id)
            await s.delete(row)
        report.deleted += 1
    async with sessions.begin() as s:
        (await s.get(ConnectorSource, source_id)).last_synced_at = func.now()
    return report


async def run(database_url: str, root: Path, name: str, watch: float | None) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    sessions = async_sessionmaker(create_async_engine(database_url), expire_on_commit=False)
    async with sessions.begin() as s:
        if await s.get(ConnectorSource, name) is None:
            s.add(ConnectorSource(id=name, kind="folder", config={"path": str(root.resolve())}))
    while True:
        r = await sync_folder(sessions, name, root)
        if r.added or r.updated or r.deleted or not watch:
            print(f"{name}: +{r.added} ~{r.updated} -{r.deleted}, skipped {len(r.skipped)}", flush=True)
        if not watch:
            return
        await asyncio.sleep(watch)


def main() -> None:
    from orgbrain.config import Settings

    p = argparse.ArgumentParser(prog="orgbrain-connect", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="kind", required=True)
    f = sub.add_parser("folder")
    f.add_argument("path", type=Path)
    f.add_argument("--name", required=True, help="source id, e.g. notes")
    f.add_argument("--watch", type=float, help="seconds between syncs; omit for one sync")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings.from_env().database_url, a.path, a.name, a.watch))


if __name__ == "__main__":
    main()
