"""orgbrain search server: the search, lookup and read_doc tools over MCP streamable HTTP.

  uv run --extra app orgbrain-search                       # http://127.0.0.1:8765/mcp
  uv run --extra app orgbrain-search --dense binary        # dense index in 197 MB of RAM
  uv run --extra app orgbrain-search --backend qdrant   # Qdrant + orgbrain-models; needs both running

Long-running on purpose: indexes load once (about a minute) in a background thread, and every agent turn (Codex, the
API-key runtime, any MCP client) reuses them. Calls are serialized: the GPU models are not thread-safe.
"""

import argparse
import logging
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from entsearch.data import ROOT
from orgbrain.config import Settings
from orgbrain.search import LocalSearch, SearchBackend
from orgbrain.sources import Source
from orgbrain.tools import lookup_tool, read_doc_tool, search_tool
from orgbrain.waiting import wait_for

log = logging.getLogger("orgbrain.search")

INSTRUCTIONS = """Search a company's internal knowledge: documents from its apps (Slack, Gmail, Google Drive, Confluence, \
Jira, Linear, GitHub, HubSpot, meeting transcripts), uploaded files, and facts the team asked to remember. Use `search` \
to find documents and cite each result by its ref, `lookup` for documents containing an exact phrase, and `read_doc` for a document's full text."""


def structured(result: Any) -> dict:
    out = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if out is None:
        raise ValueError(f"tool result has no structured content: {result!r}")
    return out


def build_server(load: "Future[SearchBackend]", app=None) -> MCPServer:
    server = MCPServer("orgbrain", instructions=INSTRUCTIONS)
    lock = threading.Lock()

    def backend() -> SearchBackend:
        try:
            return load.result()
        except Exception as e:
            raise ToolError(f"search index failed to load: {e}") from e

    @server.tool(structured_output=True)
    def search(query: str, sources: list[Source] | None = None, k: int = 10, offset: int = 0) -> dict[str, Any]:
        """Search the company's documents by meaning and keywords. Returns k (1 to 20) results with ref, doc_id,
        source, title and snippet, starting at offset (page deeper with offset=10, 20, ... up to 100). Pass sources
        only when the question clearly points at one kind of system; if filtered results look unrelated, search again
        without the filter. Cite results as [ref]."""
        with lock:
            try:
                return search_tool(backend(), query, [s.value for s in sources] if sources else None, k, offset)
            except ValueError as e:
                raise ToolError(str(e)) from e

    @server.tool(structured_output=True)
    def lookup(phrase: str, sources: list[Source] | None = None, k: int = 10) -> dict[str, Any]:
        """Documents whose title or text contains this exact phrase (case-insensitive): a ticket key, a metric or
        config name, a customer, a person, a date as written. Use it for specifics that search ranks poorly, and to
        check which documents mention a name. Snippets show the phrase in context. Cite results as [ref]."""
        try:
            return lookup_tool(backend(), phrase, [s.value for s in sources] if sources else None, k)
        except (ValueError, NotImplementedError) as e:
            raise ToolError(str(e)) from e

    @server.tool(structured_output=True)
    def read_doc(doc_id: str, offset: int = 0) -> dict[str, Any]:
        """Text of one document by doc_id, 12,000 characters at a time. If next_offset is set, the document goes on:
        call again with offset=next_offset to read the rest."""
        try:
            return read_doc_tool(backend(), doc_id, offset)
        except (LookupError, ValueError) as e:
            raise ToolError(str(e)) from e

    if app is not None:
        @server.tool(structured_output=True)
        async def propose_memory(fact: str, proposed_by: str | None = None) -> dict[str, Any]:
            """Propose a fact, decision or convention the company should keep knowing. An admin reviews it before it
            becomes searchable as source `memory`. Pass proposed_by as the teammate's id when you know it."""
            if not fact.strip():
                raise ToolError("fact is empty")
            mid = await app.memories.propose(fact, proposed_by)
            return {"id": mid, "status": "pending", "note": "An admin reviews it on the Memory page before it is searchable."}

    return server


def make_backend(name: str, data_dir: Path, dense: str, device: str) -> SearchBackend:
    if name == "local":
        return LocalSearch.load(data_dir, dense=dense, device=device)
    if name == "qdrant":
        from orgbrain.qdrant_store import CHUNKS, DOCS, QdrantSearch

        backend = QdrantSearch.connect(Settings.from_env())
        wait_for(backend.client.get_collections, "qdrant")
        log.info("model service: %s", wait_for(backend.models.health, "model service"))
        for c in (DOCS, CHUNKS):
            log.info("%s: %s points", c, backend.client.count(c).count)
        return backend
    raise ValueError(f"unknown backend {name!r}; use local or qdrant")


def start_loading(backend: str, data_dir: Path, dense: str, device: str) -> "Future[SearchBackend]":
    fut: Future = Future()

    def run() -> None:
        try:
            log.info("loading %s backend", backend)
            fut.set_result(make_backend(backend, data_dir, dense, device))
            log.info("ready")
        except Exception as e:
            log.exception("backend failed to load")
            fut.set_exception(e)

    threading.Thread(target=run, name="orgbrain-load", daemon=True).start()
    return fut


def main() -> None:
    p = argparse.ArgumentParser(prog="orgbrain-search", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["local", "qdrant"], default="qdrant")
    p.add_argument("--data-dir", type=Path, default=ROOT / "data")
    p.add_argument("--dense", choices=["fp16", "binary"], default="fp16")
    p.add_argument("--device", default="cuda")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(message)s")
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from orgbrain.memory import AppStores, MemoryStore

    sessions = async_sessionmaker(create_async_engine(Settings.from_env().database_url), expire_on_commit=False)
    app = AppStores(MemoryStore(sessions))
    build_server(start_loading(a.backend, a.data_dir, a.dense, a.device), app).run("streamable-http", host=a.host, port=a.port)


if __name__ == "__main__":
    main()
