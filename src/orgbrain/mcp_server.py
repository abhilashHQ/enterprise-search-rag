"""orgbrain search server: the search and read_doc tools over MCP streamable HTTP.

  uv run --extra app orgbrain-search                       # http://127.0.0.1:8765/mcp
  uv run --extra app orgbrain-search --dense binary        # dense index in 197 MB of RAM

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
from orgbrain.search import LocalSearch, SearchBackend
from orgbrain.sources import Source
from orgbrain.tools import read_doc_tool, search_tool

log = logging.getLogger("orgbrain.search")

INSTRUCTIONS = """Search a company's internal knowledge: documents from its apps (Slack, Gmail, Google Drive, Confluence, \
Jira, Linear, GitHub, HubSpot, meeting transcripts), uploaded files, and facts the team asked to remember. Use `search` \
to find documents and cite each result by its ref, and `read_doc` for a document's full text."""


def structured(result: Any) -> dict:
    out = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if out is None:
        raise ValueError(f"tool result has no structured content: {result!r}")
    return out


def build_server(load: "Future[SearchBackend]") -> MCPServer:
    server = MCPServer("orgbrain", instructions=INSTRUCTIONS)
    lock = threading.Lock()

    def backend() -> SearchBackend:
        try:
            return load.result()
        except Exception as e:
            raise ToolError(f"search index failed to load: {e}") from e

    @server.tool(structured_output=True)
    def search(query: str, sources: list[Source] | None = None, k: int = 10) -> dict[str, Any]:
        """Search the company's documents. Returns the top k (1 to 20) results with ref, doc_id, source, title and
        snippet. Pass sources only when the question clearly points at one kind of system; if filtered results look
        unrelated, search again without the filter. Cite results as [ref]."""
        with lock:
            try:
                return search_tool(backend(), query, [s.value for s in sources] if sources else None, k)
            except ValueError as e:
                raise ToolError(str(e)) from e

    @server.tool(structured_output=True)
    def read_doc(doc_id: str) -> dict[str, Any]:
        """Full text of one document by doc_id, from a search result (long documents are truncated)."""
        try:
            return read_doc_tool(backend(), doc_id)
        except LookupError as e:
            raise ToolError(str(e)) from e

    return server


def start_loading(data_dir: Path, dense: str, device: str) -> "Future[SearchBackend]":
    fut: Future = Future()

    def run() -> None:
        try:
            log.info("loading indexes from %s (dense=%s, device=%s)", data_dir, dense, device)
            fut.set_result(LocalSearch.load(data_dir, dense=dense, device=device))
            log.info("ready")
        except Exception as e:
            log.exception("index load failed")
            fut.set_exception(e)

    threading.Thread(target=run, name="orgbrain-load", daemon=True).start()
    return fut


def main() -> None:
    p = argparse.ArgumentParser(prog="orgbrain-search", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, default=ROOT / "data")
    p.add_argument("--dense", choices=["fp16", "binary"], default="fp16")
    p.add_argument("--device", default="cuda")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(message)s")
    build_server(start_loading(a.data_dir, a.dense, a.device)).run("streamable-http", host=a.host, port=a.port)


if __name__ == "__main__":
    main()
