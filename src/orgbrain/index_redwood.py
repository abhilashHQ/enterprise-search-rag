"""Load the Redwood demo company into Qdrant from today's research indexes (no re-embedding).

  docker compose up -d
  uv run --extra app orgbrain-index-redwood                      # documents, then chunks, then HNSW build
  uv run --extra app orgbrain-index-redwood --skip-docs --from-shard 12    # resume
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import scipy.sparse as sp
from qdrant_client import QdrantClient, models
from tqdm import tqdm

from entsearch.data import ROOT
from entsearch.docstore import DocStore
from orgbrain.bm25 import doc_vector, term_id
from orgbrain.config import Settings
from orgbrain.qdrant_store import CHUNKS, DOCS, chunk_point_id, doc_point_id, ensure_collections


def load_docs(client: QdrantClient, index: Path, batch: int) -> None:
    sparse_dir = index / "sparse"
    doc_ids = sparse_dir.joinpath("doc_ids.txt").read_text(encoding="utf8").splitlines()
    vocab = sparse_dir.joinpath("vocab.txt").read_text(encoding="utf8").splitlines()
    hashes = np.fromiter((term_id(t) for t in vocab), dtype=np.uint32, count=len(vocab))
    print(f"vocab {len(vocab):,} terms, {len(vocab) - len(np.unique(hashes)):,} lose a distinct id to hash collisions")
    doc_len = np.load(sparse_dir / "doc_len.npy")
    avgdl = float(doc_len.mean())
    tf = sp.load_npz(sparse_dir / "tf.npz").tocsr()
    store = DocStore(index / "docstore.sqlite")
    if len(store.sources()) != len(doc_ids):
        raise ValueError(f"doc store has {len(store.sources()):,} docs, sparse index {len(doc_ids):,}; rebuild one")

    def points():
        for s in range(0, len(doc_ids), 1000):
            ids = doc_ids[s : s + 1000]
            got = store.get(ids)
            for r, d in enumerate(ids, s):
                lo, hi = tf.indptr[r], tf.indptr[r + 1]
                idx, val = doc_vector(hashes[tf.indices[lo:hi]], tf.data[lo:hi], int(doc_len[r]), avgdl)
                source, title, content = got[d]
                yield models.PointStruct(id=doc_point_id(d), vector={"bm25": models.SparseVector(indices=idx, values=val)},
                                         payload={"doc_id": d, "source": source, "title": title, "content": content})

    client.upload_points(DOCS, tqdm(points(), total=len(doc_ids), desc="documents"), batch_size=batch, max_retries=5)


def load_chunks(client: QdrantClient, index: Path, vectors: str, from_shard: int, batch: int) -> None:
    sources = DocStore(index / "docstore.sqlite").sources()
    shards = sorted((index / vectors).glob("shard_*.npy"))
    for n, path in enumerate(shards):
        if n < from_shard:
            continue
        meta = pq.read_table(path.with_suffix(".parquet"), columns=["doc_id", "chunk_idx"]).to_pydict()
        vecs = np.load(path, mmap_mode="r")
        src = sources.reindex(meta["doc_id"]).to_numpy()
        client.upload_collection(
            CHUNKS, vectors={"dense": np.asarray(vecs, dtype=np.float32)},
            payload=({"doc_id": d, "source": s, "chunk_idx": int(i)} for d, s, i in zip(meta["doc_id"], src, meta["chunk_idx"])),
            ids=(chunk_point_id(d, int(i)) for d, i in zip(meta["doc_id"], meta["chunk_idx"])),
            batch_size=batch, max_retries=5)
        print(f"shard {n}: {len(vecs):,} chunks", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(prog="orgbrain-index-redwood", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--index-dir", type=Path, default=ROOT / "data/index")
    p.add_argument("--vectors", default="dense_qwen3-0.6b_c512")
    p.add_argument("--skip-docs", action="store_true")
    p.add_argument("--skip-chunks", action="store_true")
    p.add_argument("--from-shard", type=int, default=0)
    p.add_argument("--batch", type=int, default=256)
    a = p.parse_args()
    client = QdrantClient(url=Settings.from_env().qdrant_url, timeout=300)
    ensure_collections(client, bulk=True)
    if not a.skip_docs:
        load_docs(client, a.index_dir, a.batch)
    if not a.skip_chunks:
        load_chunks(client, a.index_dir, a.vectors, a.from_shard, a.batch)
    client.update_collection(CHUNKS, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000))
    while (info := client.get_collection(CHUNKS)).status != models.CollectionStatus.GREEN:
        print(f"indexing chunks: {info.indexed_vectors_count or 0:,} of {info.points_count:,}", flush=True)
        time.sleep(30)
    for name in (DOCS, CHUNKS):
        print(name, client.count(name, exact=True).count)


if __name__ == "__main__":
    main()
