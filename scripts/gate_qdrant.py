"""Migration gate: recall@10 on the 150 dev questions, Qdrant stack vs today's stack, same config (no router, hybrid
RRF k=60, rerank depth 20). Needs compose up, orgbrain-index-redwood done, orgbrain-models running.

  uv run --extra app python scripts/gate_qdrant.py
"""

import json
import time

import numpy as np

from entsearch.data import ROOT, load_questions
from entsearch.metrics import recall_at_k
from entsearch.stats import bootstrap_ci, paired_bootstrap
from orgbrain.config import Settings
from orgbrain.qdrant_store import QdrantSearch

OUT = ROOT / "data/gate/qdrant.json"


def main() -> None:
    q = load_questions("dev")
    with open(ROOT / "runs/hybrid_rrf_k60/candidates.jsonl", encoding="utf8") as f:
        old_fused = {r["question_id"]: r["document_ids"] for r in map(json.loads, f)}
    old_final = {k: v["ranked"] for k, v in json.loads((ROOT / "data/bakeoff/rerank_current.json").read_text()).items()}
    s = QdrantSearch.connect(Settings.from_env())
    rows = {}
    for r in q.itertuples():
        t0 = time.perf_counter()
        fused = [d for d, _ in s.fuse(r.question, None)]
        final = [h.doc_id for h in s.search(r.question, None, 10)]
        rows[r.question_id] = {"fused": fused, "final": final, "seconds": round(time.perf_counter() - t0, 2)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows))
    keep = [i for i, g in enumerate(q.expected_doc_ids) if g]

    def rec(lists):
        return np.array([recall_at_k(lists[q.question_id[i]], q.expected_doc_ids[i], 10) for i in keep]) * 100

    secs = [v["seconds"] for v in rows.values()]
    print(f"{len(keep)} dev questions with gold; search p50 {np.median(secs):.1f}s p90 {np.quantile(secs, 0.9):.1f}s "
          "(fuse runs twice per question here)")
    verdict = None
    for name, new, old in (("hybrid, before rerank", {k: v["fused"] for k, v in rows.items()}, old_fused),
                           ("full search", {k: v["final"] for k, v in rows.items()}, old_final)):
        a, b = rec(new), rec(old)
        m, lo, hi = bootstrap_ci(a)
        d, dlo, dhi = paired_bootstrap(a, b)
        print(f"{name:<22} new {m:.1f} [{lo:.1f},{hi:.1f}]  old {b.mean():.1f}  diff {d:+.1f} [{dlo:+.1f},{dhi:+.1f}]")
        verdict = "FAIL" if dhi < 0 else "PASS"
    print("gate:", verdict)


if __name__ == "__main__":
    main()
