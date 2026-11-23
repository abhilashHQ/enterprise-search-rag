from pathlib import Path

import numpy as np

from entsearch.serve.pipeline import Config, Pipeline


class FakeDocs:
    def get(self, ids):
        return {d: ("jira", f"title {d}", f"content {d}") for d in ids}


class FakeReranker:
    def __init__(self):
        self.seen = []

    def score(self, query, texts):
        self.seen.append(len(texts))
        return np.arange(len(texts), dtype=np.float32)


def make(rerank_depth=3, router=True):
    p = Pipeline.__new__(Pipeline)
    p.cfg = Config(data_dir=Path("."), router=router, rerank=True, verify=False, rerank_depth=rerank_depth)
    p.docs, p.dense, p.encoder, p.reranker = FakeDocs(), None, None, FakeReranker()
    p.bm25_calls, p.route_calls = [], []

    def bm25(query, sources=None):
        p.bm25_calls.append(sources)
        return ["a", "b", "c", "d", "e"]

    def route(query):
        p.route_calls.append(query)
        return ["slack"], 0.0

    p._bm25, p.route, p._release_gpu_cache = bm25, route, lambda: None
    return p


def test_explicit_sources_skip_router_and_filter_hard():
    p = make()
    res = p.search("q", k=5, sources=["jira"])
    assert p.route_calls == []
    assert p.bm25_calls == [["jira"]]
    assert res.routed_sources == []


def test_no_sources_keeps_router_behaviour():
    p = make()
    p.search("q", k=5)
    assert p.route_calls == ["q"]
    assert p.bm25_calls == [None, ["slack"]]


def test_rerank_scores_only_the_head_and_keeps_tail_order():
    p = make(rerank_depth=3)
    res = p.search("q", k=5, sources=["jira"])
    assert p.reranker.seen == [3]
    assert [h.doc_id for h in res.hits] == ["c", "b", "a", "d", "e"]
    assert res.hits[3].rerank_score is None and res.hits[0].rerank_score == 2.0


def test_default_rerank_depth_is_unchanged():
    assert Config(data_dir=Path(".")).rerank_depth == 100
