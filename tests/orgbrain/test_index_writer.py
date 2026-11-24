import hashlib
import sqlite3

import pytest
from qdrant_client import QdrantClient

from orgbrain.fts import PhraseIndex, build
from orgbrain.index_writer import IndexWriter, NewDoc
from orgbrain.qdrant_store import CHUNKS, QdrantSearch, ensure_collections


class FakeModels:
    def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0, float(i)] for i, _ in enumerate(texts)]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0, 0.0]

    def rerank(self, query, documents):
        return [0.0] * len(documents)


def digest(*paths):
    return [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


@pytest.fixture
def stores(tmp_path):
    docstore, fts = tmp_path / "docstore.sqlite", tmp_path / "fts.sqlite"
    con = sqlite3.connect(docstore)
    con.execute("CREATE TABLE docs (doc_id TEXT PRIMARY KEY, source_type TEXT, title TEXT, content TEXT)")
    con.execute("INSERT INTO docs VALUES ('rw1', 'confluence', 'Freeze policy', 'Each deploy freeze is announced in #eng.')")
    con.commit()
    con.close()
    build(docstore, fts)
    client = QdrantClient(":memory:")
    ensure_collections(client, dim=4)
    return client, docstore, fts, tmp_path / "live" / "live.sqlite"


def test_upsert_makes_a_doc_searchable_everywhere_and_delete_removes_it(stores):
    client, docstore, fts, live = stores
    redwood = digest(docstore, fts)
    w = IndexWriter(client, FakeModels(), avgdl=10.0, live=live)
    vec = w.upsert(NewDoc("file:notes:freeze.md", "files", "freeze.md", "The deploy freeze starts December 15."))
    assert vec == [1.0, 0.0, 0.0, 0.0]
    search = QdrantSearch(client, FakeModels(), phrases=PhraseIndex(fts, docstore, live))
    assert [h.doc_id for h in search.search("deploy freeze", None, 5)] == ["file:notes:freeze.md"]
    assert [h.doc_id for h in search.lookup("December 15", None, 5)] == ["file:notes:freeze.md"]
    assert {h.doc_id for h in search.lookup("deploy freeze", None, 5)} == {"rw1", "file:notes:freeze.md"}
    assert [h.doc_id for h in search.lookup("deploy freeze", ["files"], 5)] == ["file:notes:freeze.md"]
    assert [h.doc_id for h in search.lookup("deploy freeze", None, 1)] == ["file:notes:freeze.md"]
    assert search.read_doc("file:notes:freeze.md").content.startswith("The deploy freeze")

    w.upsert(NewDoc("file:notes:freeze.md", "files", "freeze.md", "The deploy freeze moved to January 5."))
    assert search.lookup("December 15", None, 5) == []
    assert [h.doc_id for h in search.lookup("January 5", None, 5)] == ["file:notes:freeze.md"]

    assert w.delete("file:notes:freeze.md") == [1.0, 0.0, 0.0, 0.0]
    assert search.search("deploy freeze", None, 5) == [] and search.lookup("January", None, 5) == []
    assert [h.doc_id for h in search.lookup("deploy freeze", None, 5)] == ["rw1"]
    assert client.count(CHUNKS).count == 0 and w.delete("file:notes:freeze.md") is None
    assert digest(docstore, fts) == redwood
