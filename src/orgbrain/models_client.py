import httpx


class ModelsClient:
    def __init__(self, url: str, http: httpx.Client | None = None, timeout: float = 120):
        self.http = http or httpx.Client(base_url=url, timeout=timeout)

    def _post(self, path: str, body: dict) -> dict:
        r = self.http.post(path, json=body)
        r.raise_for_status()
        return r.json()

    def embed_query(self, text: str) -> list[float]:
        return self._post("/embed", {"texts": [text]})["vectors"][0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._post("/embed", {"texts": texts, "kind": "document"})["vectors"]

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        return self._post("/rerank", {"query": query, "documents": documents})["scores"]

    def health(self) -> dict:
        r = self.http.get("/health")
        r.raise_for_status()
        return r.json()
