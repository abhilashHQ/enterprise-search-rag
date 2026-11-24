"""Writes one document into every index search reads: Qdrant documents (BM25 sparse + full text), Qdrant chunks
(dense), and the live store (orgbrain.fts.ensure_live) for phrase lookup. The ingest worker is the only writer; the
Redwood docstore and FTS files are never touched."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient, models

from entsearch.data import doc_text
from entsearch.index.chunking import CHUNK_SIZE, chunk_text
from orgbrain.bm25 import doc_vector_from_text
from orgbrain.fts import ensure_live
from orgbrain.qdrant_store import CHUNKS, DOCS, chunk_point_id, doc_point_id


@dataclass
class NewDoc:
    doc_id: str
    source: str
    title: str
    content: str


class IndexWriter:
    def __init__(self, client: QdrantClient, models_, avgdl: float, live: Path):
        self.client, self.models, self.avgdl = client, models_, avgdl
        ensure_live(live)
        self.db = sqlite3.connect(live, timeout=30, check_same_thread=False)

    def _by_doc(self, doc_id: str) -> models.Filter:
        return models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))])

    def _first_vector(self, doc_id: str) -> list[float] | None:
        pts = self.client.retrieve(CHUNKS, ids=[chunk_point_id(doc_id, 0)], with_vectors=["dense"])
        return list(pts[0].vector["dense"]) if pts else None

    def _drop(self, doc_id: str) -> None:
        self.client.delete(CHUNKS, models.FilterSelector(filter=self._by_doc(doc_id)), wait=True)
        self.client.delete(DOCS, models.PointIdsList(points=[doc_point_id(doc_id)]), wait=True)
        row = self.db.execute("SELECT rowid, title, content FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
        if row:
            self.db.execute("INSERT INTO fts(fts, rowid, title, content) VALUES('delete', ?, ?, ?)", row)
            self.db.execute("DELETE FROM docs WHERE rowid = ?", (row[0],))

    def upsert(self, doc: NewDoc) -> list[float]:
        text = doc_text(doc.title, doc.content)
        vecs = self.models.embed_documents(chunk_text(text, CHUNK_SIZE))
        idx, val = doc_vector_from_text(text, self.avgdl)
        self._drop(doc.doc_id)
        self.client.upsert(DOCS, [models.PointStruct(
            id=doc_point_id(doc.doc_id), vector={"bm25": models.SparseVector(indices=idx, values=val)},
            payload={"doc_id": doc.doc_id, "source": doc.source, "title": doc.title, "content": doc.content})], wait=True)
        self.client.upsert(CHUNKS, [models.PointStruct(
            id=chunk_point_id(doc.doc_id, i), vector={"dense": v},
            payload={"doc_id": doc.doc_id, "source": doc.source, "chunk_idx": i}) for i, v in enumerate(vecs)], wait=True)
        cur = self.db.execute("INSERT INTO docs (doc_id, source_type, title, content) VALUES (?, ?, ?, ?)",
                              (doc.doc_id, doc.source, doc.title, doc.content))
        self.db.execute("INSERT INTO fts(rowid, title, content) VALUES (?, ?, ?)", (cur.lastrowid, doc.title, doc.content))
        self.db.commit()
        return list(vecs[0])

    def delete(self, doc_id: str) -> list[float] | None:
        first = self._first_vector(doc_id)
        self._drop(doc_id)
        self.db.commit()
        return first
