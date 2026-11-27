"""Reranker bake-off on the 150 dev questions, laptop GPU (RTX 3050 6 GB).

Every model re-sorts the same candidates: the top DEPTH docs of the current hybrid run (runs/hybrid_rrf_k60, no
router), doc text = title + content as in production. Reports recall@10 after reranking, paired bootstrap vs the current
Qwen3-Reranker-0.6B, and measured seconds per question.

  current   Qwen3-Reranker-0.6B scores stored in runs/rerank_qwen3/scores.jsonl (pointwise, so re-sorting the top DEPTH
            by those scores is exact; no GPU)
  cohere    Cohere Rerank 3.5 on Bedrock us-east-1 (about $0.002 per question)
  others    sentence-transformers CrossEncoder, fp16, max_length per MODELS

  uv run --extra models python scripts/bakeoff_rerank.py run <name>
  uv run --extra models python scripts/bakeoff_rerank.py report
"""

import json
import sys
import time

import numpy as np

from entsearch.data import ROOT, doc_text, load_questions
from entsearch.docstore import DocStore
from entsearch.metrics import recall_at_k
from entsearch.stats import bootstrap_ci, paired_bootstrap

OUT = ROOT / "data/bakeoff"
DEPTH = 20
MODELS = {  # name: (hf id, max_length, batch_size, trust_remote_code)
    "mxbai_large": ("mixedbread-ai/mxbai-rerank-large-v2", 4096, 2, False),
    "mxbai_base": ("mixedbread-ai/mxbai-rerank-base-v2", 4096, 4, False),
    "zerank_small": ("zeroentropy/zerank-1-small", 4096, 2, True),
    "gte_modernbert": ("Alibaba-NLP/gte-reranker-modernbert-base", 4096, 8, False),
    "bge_m3": ("BAAI/bge-reranker-v2-m3", 1024, 8, False),
}


def jsonl(path) -> dict[str, list[str]]:
    with open(path, encoding="utf8") as f:
        return {r["question_id"]: r["document_ids"] for r in map(json.loads, f)}


def setup():
    q = load_questions("dev")
    hybrid = jsonl(ROOT / "runs/hybrid_rrf_k60/candidates.jsonl")
    cands = {qid: hybrid[qid][:DEPTH] for qid in q.question_id}
    return q, cands


def run(name: str) -> None:
    q, cands = setup()
    out = {}
    if name == "current":
        with open(ROOT / "runs/rerank_qwen3/scores.jsonl", encoding="utf8") as f:
            stored = {r["question_id"]: dict(zip(r["document_ids"], r["scores"])) for r in map(json.loads, f)}
        for qid, c in cands.items():
            missing = [d for d in c if d not in stored.get(qid, {})]
            if missing:
                raise ValueError(f"{qid}: {len(missing)} of {len(c)} candidates have no stored Qwen3 score")
            s = np.array([stored[qid][d] for d in c])
            out[qid] = {"ranked": [c[i] for i in np.argsort(-s, kind="stable")], "seconds": None}
    else:
        store = DocStore(ROOT / "data/index/docstore.sqlite")
        if name == "cohere":
            import boto3

            client = boto3.client("bedrock-runtime", region_name="us-east-1")

            def score(query, texts):
                body = {"api_version": 2, "query": query, "documents": texts, "top_n": len(texts)}
                res = json.loads(client.invoke_model(modelId="cohere.rerank-v3-5:0", body=json.dumps(body))["body"].read())
                s = np.zeros(len(texts))
                for r in res["results"]:
                    s[r["index"]] = r["relevance_score"]
                return s
        else:
            import torch
            from sentence_transformers import CrossEncoder

            hf, max_len, bs, remote = MODELS[name]
            model = CrossEncoder(hf, device="cuda", max_length=max_len, trust_remote_code=remote,
                                 model_kwargs={"dtype": torch.float16})

            def score(query, texts):
                s = model.predict([(query, t) for t in texts], batch_size=bs, convert_to_numpy=True)
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                return np.asarray(s, dtype=np.float32).reshape(len(texts), -1)[:, -1]
        for row in q.itertuples():
            c = cands[row.question_id]
            docs = store.get(c)
            texts = [doc_text(docs[d][1], docs[d][2]) for d in c]
            t0 = time.perf_counter()
            s = score(row.question, texts)
            dt = time.perf_counter() - t0
            out[row.question_id] = {"ranked": [c[i] for i in np.argsort(-s, kind="stable")], "seconds": round(dt, 3)}
    (OUT / f"rerank_{name}.json").write_text(json.dumps(out))
    secs = [v["seconds"] for v in out.values() if v["seconds"] is not None]
    print(f"{name}: done" + (f", p50 {np.median(secs):.1f}s p90 {np.quantile(secs, 0.9):.1f}s per question" if secs else ""))


def report() -> None:
    q, cands = setup()
    keep = [i for i, g in enumerate(q.expected_doc_ids) if g]
    names = [n for n in ["current", "cohere", *MODELS] if (OUT / f"rerank_{n}.json").exists()]
    res = {}
    for n in names:
        r = json.loads((OUT / f"rerank_{n}.json").read_text())
        rec = np.array([recall_at_k(r[q.question_id[i]]["ranked"], q.expected_doc_ids[i], 10) for i in keep]) * 100
        secs = [v["seconds"] for v in r.values() if v["seconds"] is not None]
        res[n] = (rec, secs)
    no_rerank = np.array([recall_at_k(cands[q.question_id[i]], q.expected_doc_ids[i], 10) for i in keep]) * 100
    print(f"{len(keep)} dev questions with gold, top-{DEPTH} hybrid candidates; no rerank R@10 {no_rerank.mean():.1f}\n")
    print(f"{'reranker':<16}{'R@10':>22}{'vs current':>24}{'p50 s/q':>10}{'p90 s/q':>10}")
    for n in names:
        rec, secs = res[n]
        m, lo, hi = bootstrap_ci(rec)
        row = f"{n:<16}{m:>8.1f} [{lo:5.1f},{hi:5.1f}]"
        if n == "current":
            row += f"{'':>24}"
        else:
            d, dlo, dhi = paired_bootstrap(rec, res["current"][0])
            row += f"{d:>+8.1f} [{dlo:+5.1f},{dhi:+5.1f}]"
        row += f"{np.median(secs):>10.1f}{np.quantile(secs, 0.9):>10.1f}" if secs else f"{'-':>10}{'-':>10}"
        print(row)


if __name__ == "__main__":
    report() if sys.argv[1] == "report" else run(sys.argv[2])
