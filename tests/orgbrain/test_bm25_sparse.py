from collections import Counter

import numpy as np
import scipy.sparse as sp

from entsearch.analysis import tokenize
from entsearch.retrieval.bm25 import BM25
from orgbrain.bm25 import doc_vector, doc_vector_from_text, query_vector, sparse, term_id

DOCS = ["the canary rollback runbook for perf canary", "billing owner is grace", "rollback the billing service canary",
        "lunch plans"]


def test_term_id_is_stable_u32():
    assert term_id("canary") == term_id("canary")
    assert 0 <= term_id("canary") < 2**32 and term_id("canary") != term_id("rollback")


def test_sparse_sums_collisions_and_sorts():
    assert sparse(np.array([5, 2, 5]), np.array([1.0, 2.0, 0.5])) == ([2, 5], [2.0, 1.5])


def score_like_qdrant(qvec, dvecs):
    n = len(dvecs)
    df = Counter(i for ids, _ in dvecs for i in ids)
    idf = {t: np.log1p((n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    out = []
    for ids, vals in dvecs:
        d = dict(zip(ids, vals))
        out.append(sum(qv * idf[t] * d[t] for t, qv in zip(*qvec) if t in d))
    return np.array(out)


def test_scores_match_the_research_bm25():
    toks = [tokenize(d) for d in DOCS]
    vocab = {t: i for i, t in enumerate(sorted({t for ts in toks for t in ts}))}
    rows, cols, vals = [], [], []
    for r, ts in enumerate(toks):
        for t, c in Counter(ts).items():
            rows.append(r), cols.append(vocab[t]), vals.append(c)
    tf = sp.csc_matrix((vals, (rows, cols)), shape=(len(DOCS), len(vocab)))
    doc_len = np.array([len(t) for t in toks])
    ref = BM25().fit(tf, doc_len)
    query = "canary rollback canary"
    expected = ref.score([vocab[t] for t in tokenize(query) if t in vocab])
    avgdl = doc_len.mean()
    dvecs = [doc_vector_from_text(d, avgdl) for d in DOCS]
    assert np.allclose(score_like_qdrant(query_vector(query), dvecs), expected, rtol=1e-5)


def test_doc_vector_from_counts_equals_from_text():
    text, avgdl = DOCS[0], 6.0
    counts = Counter(tokenize(text))
    ids = np.array([term_id(t) for t in counts])
    via_counts = doc_vector(ids, np.array(list(counts.values())), len(tokenize(text)), avgdl)
    assert via_counts == doc_vector_from_text(text, avgdl)


def test_query_vector_counts_repeats_and_empty_query():
    ids, vals = query_vector("canary canary rollback")
    assert sorted(vals) == [1.0, 2.0]
    assert query_vector("") == ([], [])
