"""BM25 as Qdrant sparse vectors: doc side holds the saturated, length-normalized tf; Qdrant's IDF modifier applies
Lucene's idf at query time, so dot products equal entsearch's BM25 scores. Term ids are 32-bit hashes, so no vocabulary
has to be stored or loaded; colliding terms share an id (the Redwood build reports how many)."""

import hashlib
from collections import Counter

import numpy as np

from entsearch.analysis import tokenize

K1, B = 1.2, 0.75


def term_id(term: str) -> int:
    return int.from_bytes(hashlib.blake2b(term.encode(), digest_size=4).digest(), "little")


def sparse(ids: np.ndarray, values: np.ndarray) -> tuple[list[int], list[float]]:
    uniq, inv = np.unique(np.asarray(ids, dtype=np.uint32), return_inverse=True)
    summed = np.zeros(len(uniq), dtype=np.float64)
    np.add.at(summed, inv, np.asarray(values, dtype=np.float64))
    return uniq.tolist(), summed.astype(np.float32).tolist()


def doc_vector(term_ids: np.ndarray, tf: np.ndarray, doc_len: int, avgdl: float) -> tuple[list[int], list[float]]:
    tf = np.asarray(tf, dtype=np.float32)
    norm = np.float32(K1 * (1 - B + B * doc_len / avgdl))
    return sparse(term_ids, tf / (tf + norm))


def doc_vector_from_text(text: str, avgdl: float) -> tuple[list[int], list[float]]:
    toks = tokenize(text)
    counts = Counter(toks)
    return doc_vector(np.array([term_id(t) for t in counts], dtype=np.uint32), np.array(list(counts.values())),
                      len(toks), avgdl)


def query_vector(text: str) -> tuple[list[int], list[float]]:
    counts = Counter(tokenize(text))
    if not counts:
        return [], []
    return sparse(np.array([term_id(t) for t in counts], dtype=np.uint32), np.array(list(counts.values()), dtype=np.float64))
