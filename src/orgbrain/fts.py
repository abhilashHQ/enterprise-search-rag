"""Exact phrase lookup: a contentless SQLite FTS5 index over the docstore's titles and texts.

Lives in its own file beside the docstore and reads document text from it by rowid. Disk-backed, so it fits next to
Qdrant on a laptop (a Qdrant phrase index over the full texts needed more than 7 GB of RAM to build).

  uv run --extra app python -m orgbrain.fts                # builds data/index/fts.sqlite from data/index/docstore.sqlite
"""

import argparse
import sqlite3
import time
from pathlib import Path

from entsearch.data import ROOT


def build(docstore: Path, out: Path) -> None:
    out.unlink(missing_ok=True)
    con = sqlite3.connect(f"file:{out.as_posix()}", uri=True)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("CREATE VIRTUAL TABLE fts USING fts5(title, content, content='', tokenize='unicode61 remove_diacritics 2')")
    con.execute("ATTACH DATABASE ? AS store", (f"file:{docstore.as_posix()}?mode=ro",))
    con.execute("INSERT INTO fts(rowid, title, content) SELECT rowid, title, content FROM store.docs")
    con.commit()
    con.execute("INSERT INTO fts(fts) VALUES('optimize')")
    con.commit()
    con.close()


class PhraseIndex:
    def __init__(self, fts: Path, docstore: Path):
        self.con = sqlite3.connect(f"file:{fts.as_posix()}?mode=ro", uri=True, check_same_thread=False)
        self.con.execute("ATTACH DATABASE ? AS store", (f"file:{docstore.as_posix()}?mode=ro",))

    def search(self, phrase: str, sources: list[str] | None, k: int) -> list[tuple[str, str, str, str]]:
        """(doc_id, source, title, content) of documents containing the phrase, best BM25 first."""
        match = '"' + phrase.replace('"', '""') + '"'
        sql = ("SELECT d.doc_id, d.source_type, d.title, d.content FROM fts JOIN store.docs d ON d.rowid = fts.rowid "
               "WHERE fts MATCH ?")
        args: list = [match]
        if sources:
            sql += f" AND d.source_type IN ({','.join('?' * len(sources))})"
            args += sources
        return self.con.execute(sql + " ORDER BY bm25(fts) LIMIT ?", [*args, k]).fetchall()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--docstore", type=Path, default=ROOT / "data/index/docstore.sqlite")
    p.add_argument("--out", type=Path, default=ROOT / "data/index/fts.sqlite")
    a = p.parse_args()
    t0 = time.time()
    build(a.docstore, a.out)
    print(f"built {a.out} in {time.time() - t0:.0f}s, {a.out.stat().st_size / 1e9:.2f} GB")
