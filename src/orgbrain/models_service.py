"""orgbrain model service: query embeddings and reranker scores on one GPU, over HTTP.

  uv run --extra app --extra models orgbrain-models                 # http://127.0.0.1:8766, loads both models (about a minute)
"""

import argparse
import threading
from collections.abc import Callable
from typing import Literal

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel


class EmbedRequest(BaseModel):
    texts: list[str]
    kind: Literal["query", "document"] = "query"


class RerankRequest(BaseModel):
    query: str
    documents: list[str]


def create_app(embed_query: Callable[[str], np.ndarray], embed_document: Callable[[str], np.ndarray],
               rerank: Callable[[str, list[str]], np.ndarray], info: dict) -> FastAPI:
    app = FastAPI(title="orgbrain-models")
    lock = threading.Lock()

    @app.get("/health")
    def health():
        return {"status": "ok", **info}

    @app.post("/embed")
    def embed_(req: EmbedRequest):
        fn = embed_query if req.kind == "query" else embed_document
        with lock:
            return {"vectors": [np.asarray(fn(t), dtype=np.float32).tolist() for t in req.texts]}

    @app.post("/rerank")
    def rerank_(req: RerankRequest):
        if not req.documents:
            return {"scores": []}
        with lock:
            return {"scores": np.asarray(rerank(req.query, req.documents), dtype=np.float32).tolist()}

    return app


def main() -> None:
    import torch
    import uvicorn

    from entsearch.retrieval.dense import DOC_TEMPLATE, MODEL as EMBEDDER, QueryEncoder
    from entsearch.retrieval.rerank import MODEL as RERANKER, Reranker

    p = argparse.ArgumentParser(prog="orgbrain-models", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device", default="cuda")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    a = p.parse_args()
    encoder = QueryEncoder(device=a.device)
    reranker = Reranker(token_budget=8192)

    def rerank(query: str, docs: list[str]) -> np.ndarray:
        try:
            return reranker.score(query, docs)
        finally:
            if a.device == "cuda":
                torch.cuda.empty_cache()

    uvicorn.run(create_app(encoder, lambda t: encoder.encode(t, DOC_TEMPLATE), rerank,
                           {"embedder": EMBEDDER, "reranker": RERANKER}), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
