"""Embedding bake-off on a dev candidate pool, laptop GPU.

Pool = union over dev questions of the current dense top-100 and BM25 top-100, plus every dev gold doc, plus
RANDOM_DOCS random corpus docs. Chunked exactly like the production index (512 cl100k tokens, 10% overlap). Each model
embeds the pool's chunks; every dev question is then scored against the whole pool (MaxP per doc).

Configs:
  current       stored vectors of data/index/dense_qwen3-0.6b_c512 and its stored query vectors (no EOS), i.e. today
  qwen3_st      Qwen/Qwen3-Embedding-0.6B through sentence-transformers (model card usage)
  harrier_06b   microsoft/harrier-oss-v1-0.6b, prompt web_search_query
  harrier_270m  microsoft/harrier-oss-v1-270m, prompt web_search_query

Reports recall@10 dense-only and hybrid (RRF k=60 of the pool dense top-100 with BM25 top-100), paired bootstrap vs
current. Bias: the pool holds the current model's own top-100, so its false positives are all present while a new
model's full-corpus false positives may be missing. Treat as a screen; the winner gets a full-corpus check.

  uv run --extra models python scripts/bakeoff_embed.py pool
  uv run --extra models python scripts/bakeoff_embed.py embed <config>
  uv run --extra models python scripts/bakeoff_embed.py report
"""

import json
import sys
import time

import numpy as np
import pyarrow.parquet as pq

from entsearch.data import ROOT, doc_text, load_questions
from entsearch.docstore import DocStore
from entsearch.index.chunking import CHUNK_SIZE, chunk_text
from entsearch.metrics import recall_at_k
from entsearch.retrieval.rrf import rrf
from entsearch.stats import bootstrap_ci, paired_bootstrap

OUT = ROOT / "data/bakeoff"
INDEX = ROOT / "data/index/dense_qwen3-0.6b_c512"
RANDOM_DOCS = 5000
QUERY_PROMPT = "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: "
MODELS = {
    "qwen3_st": ("Qwen/Qwen3-Embedding-0.6B", "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"),
    "harrier_06b": ("microsoft/harrier-oss-v1-0.6b", QUERY_PROMPT),
    "harrier_270m": ("microsoft/harrier-oss-v1-270m", QUERY_PROMPT),
}


def candidates(run: str) -> dict[str, list[str]]:
    with open(ROOT / "runs" / run / "candidates.jsonl", encoding="utf8") as f:
        return {r["question_id"]: r["document_ids"] for r in map(json.loads, f)}


def pool() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    q = load_questions("dev")
    dense, bm25 = candidates("dense_qwen3"), candidates("bm25_own")
    docs = set()
    for row in q.itertuples():
        docs.update(dense[row.question_id], bm25[row.question_id], row.expected_doc_ids)
    store = DocStore(INDEX.parent / "docstore.sqlite")
    all_ids = store.sources().index.to_numpy()
    rng = np.random.default_rng(20261123)
    docs.update(rng.choice(all_ids, RANDOM_DOCS, replace=False).tolist())
    docs = sorted(docs)
    got = store.get(docs)
    missing = [d for d in docs if d not in got]
    if missing:
        raise ValueError(f"{len(missing)} pool docs missing from doc store, e.g. {missing[0]}")
    chunk_doc, chunk_idx, texts = [], [], []
    for d in docs:
        for j, c in enumerate(chunk_text(doc_text(got[d][1], got[d][2]), CHUNK_SIZE)):
            chunk_doc.append(d)
            chunk_idx.append(j)
            texts.append(c)
    (OUT / "pool.json").write_text(json.dumps({"chunk_doc": chunk_doc, "chunk_idx": chunk_idx}))
    (OUT / "texts.json").write_text(json.dumps(texts))
    print(f"pool: {len(docs):,} docs, {len(texts):,} chunks")


def embed_current() -> None:
    p = json.loads((OUT / "pool.json").read_text())
    want = {(d, i): n for n, (d, i) in enumerate(zip(p["chunk_doc"], p["chunk_idx"]))}
    vecs = np.zeros((len(want), 1024), dtype=np.float16)
    found = 0
    for s in sorted(INDEX.glob("shard_*.npy")):
        meta = pq.read_table(s.with_suffix(".parquet")).to_pydict()
        rows = [(r, want[k]) for r, k in enumerate(zip(meta["doc_id"], meta["chunk_idx"])) if k in want]
        if rows:
            m = np.load(s, mmap_mode="r")
            src, dst = zip(*rows)
            vecs[list(dst)] = m[list(src)]
            found += len(rows)
    if found != len(want):
        raise ValueError(f"stored index holds {found} of {len(want)} pool chunks")
    qids = json.loads((INDEX / "queries.json").read_text())
    qv = np.load(INDEX / "queries.npy")
    dev = list(load_questions("dev").question_id)
    pos = {qid: i for i, qid in enumerate(qids)}
    np.save(OUT / "current_docs.npy", vecs)
    np.save(OUT / "current_queries.npy", qv[[pos[x] for x in dev]])
    print(f"current: {found:,} stored chunk vectors")


def embed(config: str) -> None:
    if config == "current":
        return embed_current()
    from sentence_transformers import SentenceTransformer

    name, prompt = MODELS[config]
    model = SentenceTransformer(name, device="cuda", model_kwargs={"dtype": "float16"})
    model.max_seq_length = 1024
    texts = json.loads((OUT / "texts.json").read_text())
    order = np.argsort([-len(t) for t in texts], kind="stable")
    t0 = time.time()
    vecs = model.encode([texts[i] for i in order], batch_size=16, normalize_embeddings=True, show_progress_bar=True,
                        convert_to_numpy=True).astype(np.float16)
    out = np.empty_like(vecs)
    out[order] = vecs
    q = list(load_questions("dev").question)
    qv = model.encode(q, prompt=prompt, batch_size=32, normalize_embeddings=True, convert_to_numpy=True).astype(np.float16)
    np.save(OUT / f"{config}_docs.npy", out)
    np.save(OUT / f"{config}_queries.npy", qv)
    print(f"{config}: {len(texts):,} chunks in {time.time() - t0:.0f}s")


def rank(qv: np.ndarray, dv: np.ndarray, chunk_doc: np.ndarray, doc_names: list[str], depth: int = 100) -> list[list[str]]:
    sims = qv.astype(np.float32) @ dv.astype(np.float32).T
    out = []
    for s in sims:
        best = np.full(len(doc_names), -np.inf, dtype=np.float32)
        np.maximum.at(best, chunk_doc, s)
        top = np.argsort(-best, kind="stable")[:depth]
        out.append([doc_names[i] for i in top])
    return out


def report() -> None:
    p = json.loads((OUT / "pool.json").read_text())
    doc_names = sorted(set(p["chunk_doc"]))
    code = {d: i for i, d in enumerate(doc_names)}
    chunk_doc = np.array([code[d] for d in p["chunk_doc"]])
    q = load_questions("dev")
    keep = [i for i, g in enumerate(q.expected_doc_ids) if g]
    bm25 = candidates("bm25_own")
    configs = [c for c in ["current", *MODELS] if (OUT / f"{c}_docs.npy").exists()]
    res = {}
    for c in configs:
        ranked = rank(np.load(OUT / f"{c}_queries.npy"), np.load(OUT / f"{c}_docs.npy"), chunk_doc, doc_names)
        dense, hybrid = [], []
        for i in keep:
            gold = q.expected_doc_ids[i]
            fused = [d for d, _ in rrf([ranked[i], bm25[q.question_id[i]]], k=60, top_n=100)]
            dense.append(recall_at_k(ranked[i], gold, 10))
            hybrid.append(recall_at_k(fused, gold, 10))
        res[c] = (np.array(dense), np.array(hybrid))
    print(f"{len(keep)} dev questions with gold; pool {len(doc_names):,} docs, {len(chunk_doc):,} chunks\n")
    print(f"{'config':<14}{'dense R@10':>22}{'vs current':>24}{'hybrid R@10':>22}{'vs current':>24}")
    for c in configs:
        d, h = res[c]
        row = f"{c:<14}"
        for x, base in ((d, res["current"][0]), (h, res["current"][1])):
            m, lo, hi = bootstrap_ci(x * 100)
            row += f"{m:>8.1f} [{lo:5.1f},{hi:5.1f}]"
            if c == "current":
                row += f"{'':>24}"
            else:
                dm, dlo, dhi = paired_bootstrap(x * 100, base * 100)
                row += f"{dm:>+8.1f} [{dlo:+5.1f},{dhi:+5.1f}]"
        print(row)


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"pool": pool, "report": report}.get(cmd, lambda: embed(sys.argv[2]))()
