import numpy as np
from fastapi.testclient import TestClient

from orgbrain.models_client import ModelsClient
from orgbrain.models_service import create_app


def app():
    return create_app(lambda t: np.array([len(t), 0.0], dtype=np.float32),
                      lambda t: np.array([0.0, len(t)], dtype=np.float32),
                      lambda q, docs: np.array([float(len(d)) for d in docs], dtype=np.float32),
                      {"embedder": "fake-e", "reranker": "fake-r"})


def test_health_reports_models():
    assert TestClient(app()).get("/health").json() == {"status": "ok", "embedder": "fake-e", "reranker": "fake-r"}


def test_client_round_trips_embed_and_rerank():
    c = ModelsClient("http://test", http=TestClient(app()))
    assert c.embed_query("abc") == [3.0, 0.0]
    assert c.rerank("q", ["a", "bbb"]) == [1.0, 3.0]
    assert c.health()["reranker"] == "fake-r"


def test_rerank_with_no_documents():
    assert ModelsClient("http://test", http=TestClient(app())).rerank("q", []) == []


def test_document_mode_uses_the_document_encoder():
    c = ModelsClient("http://test", http=TestClient(app()))
    assert c.embed_documents(["ab", "abcd"]) == [[0.0, 2.0], [0.0, 4.0]]
    assert c.embed_query("ab") == [2.0, 0.0]
