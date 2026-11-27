"""Read documents by id from the live store (ingested after the Redwood load) and the Redwood docstore."""

import sqlite3
from pathlib import Path

from orgbrain.fts import ensure_live


class DocReader:
    def __init__(self, docstore: Path, live: Path):
        ensure_live(live)
        self._docstore, self._redwood = docstore, None
        self.live = sqlite3.connect(f"file:{live.as_posix()}?mode=ro", uri=True, timeout=30, check_same_thread=False)
        self._redwood_counts: dict[str, int] | None = None

    @property
    def redwood(self) -> sqlite3.Connection | None:
        """Opened on first use once the file exists, so an index restored by `orgbrain demo` after start is seen."""
        if self._redwood is None and self._docstore.exists():
            self._redwood = sqlite3.connect(f"file:{self._docstore.as_posix()}?mode=ro", uri=True,
                                            check_same_thread=False)
        return self._redwood

    def get(self, doc_id: str) -> dict | None:
        for con in (self.live, self.redwood):
            if con is None:
                continue
            row = con.execute("SELECT doc_id, source_type, title, content FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
            if row:
                return dict(zip(("doc_id", "source", "title", "content"), row))
        return None

    def has(self, doc_ids: list[str]) -> set[str]:
        out = set()
        for i in range(0, len(doc_ids), 500):
            batch = doc_ids[i:i + 500]
            q = f"SELECT doc_id FROM docs WHERE doc_id IN ({','.join('?' * len(batch))})"
            out |= {r[0] for r in self.live.execute(q, batch)}
        return out

    def counts(self) -> dict[str, int]:
        if self._redwood_counts is None and self.redwood is not None:
            self._redwood_counts = dict(self.redwood.execute(
                "SELECT source_type, count(*) FROM docs GROUP BY source_type").fetchall())
        out = dict(self._redwood_counts or {})
        rows = self.live.execute("SELECT doc_id, source_type FROM docs").fetchall()
        for i in range(0, len(rows), 500):
            batch = rows[i:i + 500]
            in_redwood = set()
            if self.redwood is not None:
                q = f"SELECT doc_id FROM docs WHERE doc_id IN ({','.join('?' * len(batch))})"
                in_redwood = {r[0] for r in self.redwood.execute(q, [d for d, _ in batch])}
            for doc_id, src in batch:
                if doc_id not in in_redwood:
                    out[src] = out.get(src, 0) + 1
        return out
