"""orgbrain end to end on the dev questions: Codex agent over orgbrain-search, answers judged like the October runs.

Needs orgbrain-search (http://127.0.0.1:8765/mcp) and what its backend needs (Qdrant + orgbrain-models) running.

  uv run --extra app python scripts/run_orgbrain_dev.py --run-dir runs/orgbrain_codex_medium --effort medium --judge

Writes run_dir/answers.jsonl (harness format: [ref] markers stripped, document_ids = cited docs) and run_dir/trace.jsonl
(raw answer, citations, tool calls, seconds, usage, error per question). Re-running skips answered questions.
"""

import argparse
import asyncio
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from entsearch.data import ROOT, load_questions
from orgbrain.answer import collect_hits, collect_people, finalize
from orgbrain.instructions import instructions
from orgbrain.refs import _CITE
from orgbrain.runtime.codex import CodexConfig, CodexRuntime
from orgbrain.runtime.events import Done, Message, ToolCall, ToolResult


async def answer_one(runtime: CodexRuntime, question: str) -> dict:
    start, results, calls, text, usage = time.perf_counter(), [], [], "", {}
    async for ev in runtime.run(question):
        if isinstance(ev, ToolCall):
            calls.append({"tool": ev.tool, "arguments": ev.arguments})
        elif isinstance(ev, ToolResult) and ev.result:
            results.append(ev.result)
        elif isinstance(ev, Message):
            text = ev.text
        elif isinstance(ev, Done):
            usage = ev.usage
    ans = finalize(text, collect_hits(results), collect_people(results))
    return {"raw": text, "citations": [asdict(c) for c in ans.citations], "abstained": ans.abstained,
            "unknown_refs": ans.unknown_refs, "tool_calls": calls, "usage": usage,
            "seconds": round(time.perf_counter() - start, 1)}


async def main(a: argparse.Namespace) -> None:
    q = load_questions("dev")
    if a.ids:
        q = q[q.question_id.isin(a.ids.split(","))]
    if a.limit:
        q = q.head(a.limit)
    run_dir = a.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    answers_path, trace_path = run_dir / "answers.jsonl", run_dir / "trace.jsonl"
    done = {json.loads(l)["question_id"] for l in answers_path.read_text(encoding="utf8").splitlines()} \
        if answers_path.exists() else set()
    todo = [(r.question_id, r.question) for r in q.itertuples() if r.question_id not in done]
    runtime = CodexRuntime(CodexConfig(model=a.model, effort=a.effort, workdir=ROOT / "data/codex_work"),
                           instructions(a.company))
    sem, lock, failed = asyncio.Semaphore(a.parallel), asyncio.Lock(), []
    print(f"{len(todo)} to answer, {len(done)} already done", flush=True)

    async def worker(qid: str, question: str) -> None:
        async with sem:
            for attempt in (1, 2):
                try:
                    tr = await answer_one(runtime, question)
                    break
                except Exception as e:
                    tr = {"error": str(e)[-2000:], "attempt": attempt}
            async with lock:
                with open(trace_path, "a", encoding="utf8") as f:
                    f.write(json.dumps({"question_id": qid, **tr}) + "\n")
                if "error" in tr:
                    failed.append(qid)
                    print(f"{qid} FAILED: {tr['error'][:200]}", flush=True)
                    return
                text = re.sub(r"[ \t]+([.,;:)])", r"\1", re.sub(r"[ \t]{2,}", " ", _CITE.sub("", tr["raw"]))).strip()
                row = {"question_id": qid, "answer": text, "document_ids": [c["doc_id"] for c in tr["citations"]]}
                with open(answers_path, "a", encoding="utf8") as f:
                    f.write(json.dumps(row) + "\n")
                print(f"{qid} {tr['seconds']}s {len(tr['tool_calls'])} calls {len(row['document_ids'])} cited", flush=True)

    await asyncio.gather(*(worker(*t) for t in todo))
    if failed:
        print(f"{len(failed)} failed, re-run to retry: {failed}")
        return
    if a.judge:
        from entsearch.harness import metrics_eval

        print(json.dumps(metrics_eval(run_dir, q, parallelism=8), indent=1)[:2000])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--model", default="gpt-6-luna")
    p.add_argument("--effort", default="medium")
    p.add_argument("--company", default="Redwood Inference")
    p.add_argument("--parallel", type=int, default=4)
    p.add_argument("--limit", type=int)
    p.add_argument("--ids", help="comma-separated question ids")
    p.add_argument("--judge", action="store_true")
    asyncio.run(main(p.parse_args()))
