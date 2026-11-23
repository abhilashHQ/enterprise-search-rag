from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from orgbrain.refs import ref


@dataclass
class Hit:
    ref: str
    doc_id: str
    source: str
    title: str
    snippet: str
    score: float | None


@dataclass
class Doc:
    doc_id: str
    source: str
    title: str
    content: str


class SearchBackend(Protocol):
    def search(self, query: str, sources: list[str] | None, k: int) -> list[Hit]: ...

    def read_doc(self, doc_id: str) -> Doc | None: ...


class LocalSearch:
    """The research pipeline's indexes (BM25 + dense + RRF + rerank) as an orgbrain backend."""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    @classmethod
    def load(cls, data_dir: Path, dense: str = "fp16", device: str = "cuda") -> "LocalSearch":
        from entsearch.serve.pipeline import Config, Pipeline

        return cls(Pipeline(Config(data_dir=data_dir, router=False, rerank=True, rerank_depth=20, dense=dense,
                                   device=device, verify=False)))

    def search(self, query: str, sources: list[str] | None, k: int) -> list[Hit]:
        res = self.pipeline.search(query, k=k, sources=sources)
        return [
            Hit(ref(h.doc_id), h.doc_id, h.source, h.title, h.snippet,
                h.rerank_score if h.rerank_score is not None else h.fused_score)
            for h in res.hits
        ]

    def read_doc(self, doc_id: str) -> Doc | None:
        d = self.pipeline.get_document(doc_id)
        return None if d is None else Doc(d["doc_id"], d["source"], d["title"], d["content"])
