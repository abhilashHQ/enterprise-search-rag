"""Judge leaderboard systems' published answers on our dev questions with our judge (gpt-oss-120b, no correction).

Answers and official per-question results come from the leaderboard space (data/raw_data, downloaded to
data/leaderboard/). Puts each system on the same judge as our runs, and the official scores next to ours show how
much of a gap is the judge.

  uv run --extra app python scripts/judge_leaderboard.py pipeshub codos
"""

import json
import sys

import numpy as np

from entsearch.data import ROOT, load_questions
from entsearch.harness import metrics_eval

LB = ROOT / "data/leaderboard"


def per_q(rows):
    return {r["question_id"]: (r["completeness_pct"] if r["answer_correct"] else 0.0) for r in rows}


def main(systems: list[str]) -> None:
    q = load_questions("dev")
    dev = set(q.question_id)
    for name in systems:
        run_dir = ROOT / f"runs/lb_{name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(LB / f"answers_{name}.jsonl", encoding="utf8") as f, \
                open(run_dir / "answers.jsonl", "w", encoding="utf8") as out:
            for line in f:
                row = json.loads(line)
                if row["question_id"] in dev:
                    out.write(json.dumps(row) + "\n")  # ASCII-escaped: the harness reads with the locale codec
        if not (run_dir / "eval_results.json").exists():
            metrics_eval(run_dir, q, parallelism=8)
        ours = per_q(json.loads((run_dir / "eval_results.json").read_text(encoding="utf8"))["questions"])
        official = per_q([r for r in json.loads((LB / f"results_{name}.json").read_text(encoding="utf8"))["questions"]
                          if r["question_id"] in dev])
        ids = sorted(ours)
        a, b = np.array([ours[i] for i in ids]), np.array([official[i] for i in ids])
        print(f"{name}: dev n={len(ids)}  our judge {a.mean():.1f}  official judge {b.mean():.1f}  "
              f"agree on correct/incorrect {np.mean((a > 0) == (b > 0)) * 100:.0f}%")


if __name__ == "__main__":
    main(sys.argv[1:])
