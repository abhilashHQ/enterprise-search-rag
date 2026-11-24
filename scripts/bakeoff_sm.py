"""Bake-off tasks on a SageMaker training job: tasks go round-robin over the GPUs, in parallel across GPUs and one after
another on each GPU.

Inputs (channel "data", built from data/bakeoff by the export step): texts.json.gz (pool chunks), questions.json (dev),
rerank.json.gz (top-20 hybrid candidates per dev question, doc text = title + content). Outputs go to /opt/ml/model in
the shapes scripts/bakeoff_embed.py and scripts/bakeoff_rerank.py read; embed shards are merged locally.

  python bakeoff_sm.py embed:qwen3_st:0:2 embed:qwen3_st:1:2 rerank:mxbai_large ...
"""

import gzip
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

DATA = Path("/opt/ml/input/data/data")
OUT = Path("/opt/ml/model")
PINS = ["transformers==5.18.0", "sentence-transformers==6.1.0", "tokenizers==0.23.2", "accelerate==1.15.0",
        "huggingface-hub==1.33.0", "safetensors==0.8.0", "numpy==2.4.6"]
QUERY_PROMPT = "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: "
EMBED = {
    "qwen3_st": ("Qwen/Qwen3-Embedding-0.6B", QUERY_PROMPT.rstrip(" ")),
    "harrier_06b": ("microsoft/harrier-oss-v1-0.6b", QUERY_PROMPT),
    "harrier_270m": ("microsoft/harrier-oss-v1-270m", QUERY_PROMPT),
}
FP32 = {"harrier_270m"}  # Gemma 3 based: activations overflow fp16 (all-NaN vectors)
RERANK = {  # name: (hf id, max_length, batch_size, trust_remote_code)
    "mxbai_large": ("mixedbread-ai/mxbai-rerank-large-v2", 4096, 4, False),
    "mxbai_base": ("mixedbread-ai/mxbai-rerank-base-v2", 4096, 8, False),
    "zerank_small": ("zeroentropy/zerank-1-small", 4096, 1, True),  # eager attention: memory grows with length squared
    "gte_modernbert": ("Alibaba-NLP/gte-reranker-modernbert-base", 4096, 20, False),
    "bge_m3": ("BAAI/bge-reranker-v2-m3", 1024, 20, False),
}


def embed(config: str, shard: int, n: int) -> None:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    name, prompt = EMBED[config]
    dtype = "float32" if config in FP32 else "float16"
    model = SentenceTransformer(name, device="cuda", model_kwargs={"dtype": dtype})
    model.max_seq_length = 1024
    with gzip.open(DATA / "texts.json.gz", "rt", encoding="utf8") as f:
        texts = json.load(f)
    order = np.argsort([-len(t) for t in texts], kind="stable")
    mine = order[shard::n]
    t0 = time.time()
    vecs = model.encode([texts[i] for i in mine], batch_size=32, normalize_embeddings=True, show_progress_bar=False,
                        convert_to_numpy=True).astype(np.float16)
    np.save(OUT / f"{config}_docs_s{shard}.npy", vecs)
    np.save(OUT / f"{config}_idx_s{shard}.npy", mine)
    if shard == 0:
        q = [r["question"] for r in json.loads((DATA / "questions.json").read_text())]
        qv = model.encode(q, prompt=prompt, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)
        np.save(OUT / f"{config}_queries.npy", qv.astype(np.float16))
    print(f"{config} shard {shard}/{n}: {len(mine):,} chunks in {time.time() - t0:.0f}s", flush=True)


def rerank(name: str) -> None:
    import numpy as np
    import torch
    from sentence_transformers import CrossEncoder

    hf, max_len, bs, remote = RERANK[name]
    model = CrossEncoder(hf, device="cuda", max_length=max_len, trust_remote_code=remote,
                         model_kwargs={"dtype": torch.float16})
    with gzip.open(DATA / "rerank.json.gz", "rt", encoding="utf8") as f:
        rows = json.load(f)
    out = {}
    for r in rows:
        t0 = time.perf_counter()
        s = model.predict([(r["question"], t) for t in r["texts"]], batch_size=bs, convert_to_numpy=True)
        torch.cuda.synchronize()
        dt = time.perf_counter() - t0
        s = np.asarray(s, dtype=np.float32).reshape(len(r["texts"]), -1)[:, -1]
        out[r["question_id"]] = {"ranked": [r["doc_ids"][i] for i in np.argsort(-s, kind="stable")], "seconds": round(dt, 3)}
    (OUT / f"rerank_{name}.json").write_text(json.dumps(out))
    secs = [v["seconds"] for v in out.values()]
    print(f"{name}: p50 {np.median(secs):.2f}s p90 {np.quantile(secs, 0.9):.2f}s per question", flush=True)


def run(task: str) -> None:
    kind, *args = task.split(":")
    embed(args[0], int(args[1]), int(args[2])) if kind == "embed" else rerank(args[0])


def main(tasks: list[str]) -> None:
    pip = [sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir"]
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "torchvision", "torchaudio"], check=False)
    subprocess.run(pip + ["torch==2.11.0", "--index-url", "https://download.pytorch.org/whl/cu128"], check=True)
    subprocess.run(pip + PINS, check=True)
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    n_gpu = len(subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, check=True).stdout.splitlines())
    status = {}

    def worker(gpu: int) -> None:
        for task in tasks[gpu::n_gpu]:
            path = OUT / "logs" / f"{task.replace(':', '_')}.log"
            env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "HF_HOME": "/tmp/hf", "TOKENIZERS_PARALLELISM": "false"}
            with open(path, "w") as log:
                status[task] = subprocess.run([sys.executable, __file__, "--run", task], stdout=log,
                                              stderr=subprocess.STDOUT, env=env).returncode
            tail = path.read_text(errors="replace").splitlines()[-15:]
            print(f"=== {task} on gpu {gpu} exit {status[task]}\n" + "\n".join(tail), flush=True)

    threads = [threading.Thread(target=worker, args=(g,)) for g in range(min(n_gpu, len(tasks)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    (OUT / "status.json").write_text(json.dumps(status))


if __name__ == "__main__":
    run(sys.argv[2]) if sys.argv[1] == "--run" else main(sys.argv[1:])
