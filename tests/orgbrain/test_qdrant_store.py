import numpy as np
import pytest
from qdrant_client import QdrantClient, models

from orgbrain.bm25 import doc_vector_from_text
from orgbrain.qdrant_store import (CHUNKS, DOCS, QdrantSearch, chunk_point_id, doc_point_id, ensure_collections,
                                   snippet_around)
from orgbrain.refs import ref
from orgbrain.search import Doc

DOCS_ROWS = [  # doc_id, source, title, content, chunk vectors (4-d)
    ("d1", "confluence", "Canary runbook", "rollback the canary with the runbook", [[1, 0, 0, 0], [0, 1, 0, 0]]),
    ("d2", "slack", "eng-releases", "canary rollback happened yesterday", [[0.9, 0.1, 0, 0]]),
    ("d3", "jira", "Billing ticket", "billing owner is grace", [[0, 0, 1, 0]]),
]


class FakeModels:
    def __init__(self, rerank_scores=None):
        self.rerank_scores = rerank_scores or {}
        self.reranked = []

    def embed_query(self, text):
        return [1.0, 0.0, 0.0, 0.0]

    def rerank(self, query, documents):
        self.reranked.append(len(documents))
        return [self.rerank_scores.get(d.split("\n\n")[0], 0.0) for d in documents]


@pytest.fixture
def client():
    c = QdrantClient(":memory:")
    ensure_collections(c, dim=4)
    def bm25(text):
        idx, val = doc_vector_from_text(text, 5.0)
        return models.SparseVector(indices=idx, values=val)

    c.upsert(DOCS, [models.PointStruct(id=doc_point_id(d), payload={"doc_id": d, "source": s, "title": t, "content": body},
                                       vector={"bm25": bm25(f"{t}\n\n{body}")}) for d, s, t, body, _ in DOCS_ROWS])
    c.upsert(CHUNKS, [models.PointStruct(id=chunk_point_id(d, i), payload={"doc_id": d, "source": s, "chunk_idx": i},
                                         vector={"dense": v})
                      for d, s, _, _, vecs in DOCS_ROWS for i, v in enumerate(vecs)])
    return c


def test_point_ids_are_deterministic_uuids():
    assert doc_point_id("d1") == doc_point_id("d1") != doc_point_id("d2")
    assert chunk_point_id("d1", 0) != chunk_point_id("d1", 1)


def test_fuse_returns_doc_level_rrf_of_bm25_and_maxp_dense(client):
    s = QdrantSearch(client, FakeModels())
    fused = [d for d, _ in s.fuse("canary rollback", None)]
    assert set(fused[:2]) == {"d1", "d2"} and fused[2] == "d3"


def test_source_filter_applies_to_both_lists(client):
    s = QdrantSearch(client, FakeModels())
    assert [d for d, _ in s.fuse("canary rollback", ["slack"])] == ["d2"]


def test_search_reranks_and_shapes_hits(client):
    m = FakeModels({"Billing ticket": 5.0, "eng-releases": 1.0})
    hits = QdrantSearch(client, m).search("canary rollback billing", None, 2)
    assert m.reranked == [3]
    assert [h.doc_id for h in hits] == ["d3", "d2"]
    assert hits[0].ref == ref("d3") and hits[0].source == "jira" and hits[0].score == 5.0
    assert hits[0].snippet == "billing owner is grace"


def test_read_doc(client):
    s = QdrantSearch(client, FakeModels())
    assert s.read_doc("d3") == Doc("d3", "jira", "Billing ticket", "billing owner is grace")
    assert s.read_doc("nope") is None


def test_no_matches_returns_empty(client):
    assert QdrantSearch(client, FakeModels()).search("zzzz", ["hubspot"], 5) == []


def test_search_offset_pages_past_the_first_results(client):
    s = QdrantSearch(client, FakeModels({"Billing ticket": 5.0, "eng-releases": 1.0}))
    assert [h.doc_id for h in s.search("canary rollback billing", None, 1, offset=1)] == ["d2"]


@pytest.fixture
def phrases(tmp_path):
    import sqlite3

    from orgbrain.fts import PhraseIndex, build

    store = tmp_path / "docstore.sqlite"
    con = sqlite3.connect(store)
    con.execute("CREATE TABLE docs (doc_id TEXT PRIMARY KEY, source_type TEXT, title TEXT, content TEXT)")
    con.executemany("INSERT INTO docs VALUES (?, ?, ?, ?)", [(d, s, t, body) for d, s, t, body, _ in DOCS_ROWS])
    con.commit()
    con.close()
    build(store, tmp_path / "fts.sqlite")
    return PhraseIndex(tmp_path / "fts.sqlite", store)


def test_lookup_matches_exact_phrase_in_content_or_title(client, phrases):
    s = QdrantSearch(client, FakeModels(), phrases=phrases)
    assert [h.doc_id for h in s.lookup("rollback happened", None, 5)] == ["d2"]
    assert [h.doc_id for h in s.lookup("billing ticket", None, 5)] == ["d3"]
    assert {h.doc_id for h in s.lookup("canary", None, 5)} == {"d1", "d2"}
    assert s.lookup("happened rollback", None, 5) == []
    assert s.lookup("billing ticket", None, 5)[0].snippet == "billing owner is grace"


def test_lookup_respects_source_filter(client, phrases):
    assert [h.doc_id for h in QdrantSearch(client, FakeModels(), phrases=phrases).lookup("canary", ["slack"], 5)] == ["d2"]


def test_lookup_without_phrase_index_is_unavailable(client):
    with pytest.raises(NotImplementedError):
        QdrantSearch(client, FakeModels()).lookup("canary", None, 5)


def test_snippet_centres_on_the_phrase():
    text = "a" * 500 + "NEEDLE" + "b" * 500
    snip = snippet_around(text, "needle", width=106)
    assert "NEEDLE" in snip and len(snip) == 106 and snip.index("NEEDLE") == 50
    assert snippet_around("short text", "absent", width=5) == "short"


def test_best_passage_finds_the_window_with_the_query_terms():
    from orgbrain.qdrant_store import best_passage

    text = "Issue summary: generic opening. " * 20 + "On 2026-03-13 the us-east pool returned 502 errors. " + "filler " * 50
    snip = best_passage(text, "what caused 502 errors in the us-east pool?", width=80)
    assert "us-east pool returned 502 errors" in snip and "generic opening" not in snip
    assert best_passage("nothing relevant", "zebra", width=7) == "nothing"
