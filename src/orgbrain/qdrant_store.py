"""Qdrant-backed search: BM25 over whole documents and dense MaxP over chunks, fused by doc, reranked.

  documents  one point per doc: sparse "bm25" (IDF modifier), payload doc_id, source, title, content (on disk)
  chunks     one point per 512-token chunk: dense "dense" (fp16 on disk, binary quantization in RAM), payload doc_id,
             source, chunk_idx
"""

import uuid
from typing import Protocol

import numpy as np
from qdrant_client import QdrantClient, models

from entsearch.data import doc_text
from entsearch.retrieval.rrf import rrf
from orgbrain.bm25 import query_vector
from orgbrain.refs import ref
from orgbrain.search import Doc, Hit

DOCS, CHUNKS = "documents", "chunks"
DIM = 1024
FUSE_DEPTH, RRF_K, RERANK_DEPTH, SNIPPET = 100, 60, 20, 300
_NS = uuid.NAMESPACE_URL


def doc_point_id(doc_id: str) -> str:
    return str(uuid.uuid5(_NS, f"orgbrain:doc:{doc_id}"))


def chunk_point_id(doc_id: str, chunk_idx: int) -> str:
    return str(uuid.uuid5(_NS, f"orgbrain:chunk:{doc_id}:{chunk_idx}"))


def ensure_collections(client: QdrantClient, dim: int = DIM, bulk: bool = False) -> None:
    if not client.collection_exists(DOCS):
        client.create_collection(
            DOCS, vectors_config={}, on_disk_payload=True,
            sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
    if not client.collection_exists(CHUNKS):
        client.create_collection(
            CHUNKS, on_disk_payload=True,
            vectors_config={"dense": models.VectorParams(size=dim, distance=models.Distance.COSINE, on_disk=True,
                                                         datatype=models.Datatype.FLOAT16)},
            quantization_config=models.BinaryQuantization(binary=models.BinaryQuantizationConfig(always_ram=True)),
            optimizers_config=models.OptimizersConfigDiff(indexing_threshold=0) if bulk else None,
        )
    for name in (DOCS, CHUNKS):
        for field in ("doc_id", "source"):
            client.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)


class Models(Protocol):
    def embed_query(self, text: str) -> list[float]: ...

    def rerank(self, query: str, documents: list[str]) -> list[float]: ...


class QdrantSearch:
    def __init__(self, client: QdrantClient, models_: Models, hnsw_ef: int = 1024, oversampling: float = 16.0):
        self.client, self.models = client, models_
        self.params = models.SearchParams(
            hnsw_ef=hnsw_ef, quantization=models.QuantizationSearchParams(rescore=True, oversampling=oversampling))

    @classmethod
    def connect(cls, settings) -> "QdrantSearch":
        from orgbrain.models_client import ModelsClient

        return cls(QdrantClient(url=settings.qdrant_url, timeout=120), ModelsClient(settings.models_url))

    @staticmethod
    def _filter(sources: list[str] | None) -> models.Filter | None:
        if not sources:
            return None
        return models.Filter(must=[models.FieldCondition(key="source", match=models.MatchAny(any=list(sources)))])

    def _bm25(self, query: str, flt) -> list[str]:
        ids, vals = query_vector(query)
        if not ids:
            return []
        res = self.client.query_points(DOCS, query=models.SparseVector(indices=ids, values=vals), using="bm25",
                                       limit=FUSE_DEPTH, query_filter=flt, with_payload=["doc_id"])
        return [p.payload["doc_id"] for p in res.points]

    def _dense(self, query: str, flt) -> list[str]:
        res = self.client.query_points_groups(
            CHUNKS, query=self.models.embed_query(query), using="dense", group_by="doc_id", limit=FUSE_DEPTH,
            group_size=1, query_filter=flt, search_params=self.params, with_payload=False)
        return [g.id for g in res.groups]

    def _docs(self, doc_ids: list[str]) -> dict[str, dict]:
        pts = self.client.retrieve(DOCS, ids=[doc_point_id(d) for d in doc_ids],
                                   with_payload=["doc_id", "source", "title", "content"])
        return {p.payload["doc_id"]: p.payload for p in pts}

    def fuse(self, query: str, sources: list[str] | None) -> list[tuple[str, float]]:
        flt = self._filter(sources)
        lists = [l for l in (self._bm25(query, flt), self._dense(query, flt)) if l]
        return rrf(lists, k=RRF_K, top_n=FUSE_DEPTH) if lists else []

    def search(self, query: str, sources: list[str] | None, k: int) -> list[Hit]:
        fused = self.fuse(query, sources)
        if not fused:
            return []
        ids = [d for d, _ in fused]
        docs = self._docs(ids[: max(k, RERANK_DEPTH)])
        head = ids[:RERANK_DEPTH]
        scores = np.asarray(self.models.rerank(query, [doc_text(docs[d]["title"], docs[d]["content"]) for d in head]))
        ranked = [head[i] for i in np.argsort(-scores, kind="stable")] + ids[RERANK_DEPTH:]
        score = {**dict(fused), **dict(zip(head, scores.tolist()))}
        return [Hit(ref(d), d, docs[d]["source"], docs[d]["title"], docs[d]["content"][:SNIPPET], score[d])
                for d in ranked[:k]]

    def read_doc(self, doc_id: str) -> Doc | None:
        pts = self.client.retrieve(DOCS, ids=[doc_point_id(doc_id)], with_payload=True)
        if not pts:
            return None
        p = pts[0].payload
        return Doc(p["doc_id"], p["source"], p["title"], p["content"])
