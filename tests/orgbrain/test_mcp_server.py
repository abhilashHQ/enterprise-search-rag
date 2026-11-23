from concurrent.futures import Future

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from orgbrain.mcp_server import build_server, structured
from orgbrain.refs import ref
from orgbrain.search import Doc, Hit


class FakeBackend:
    def search(self, query, sources, k):
        return [Hit(ref("d1"), "d1", (sources or ["jira"])[0], "T", "s", 1.0)][:k]

    def read_doc(self, doc_id):
        return Doc("d1", "jira", "T", "body") if doc_id == "d1" else None


def server():
    f: Future = Future()
    f.set_result(FakeBackend())
    return build_server(f)


def test_lists_search_and_read_doc_with_source_enum():
    tools = anyio.run(server().list_tools)
    assert {t.name for t in tools} == {"search", "read_doc"}
    search = next(t for t in tools if t.name == "search")
    assert "google_drive" in search.model_dump_json() and "memory" in search.model_dump_json()


def test_search_returns_structured_results():
    r = anyio.run(server().call_tool, "search", {"query": "x", "sources": ["slack"], "k": 1})
    out = structured(r)
    assert out["results"][0]["source"] == "slack" and out["results"][0]["ref"] == ref("d1")


def test_unknown_doc_is_a_tool_error():
    with pytest.raises(ToolError, match="unknown doc_id"):
        anyio.run(server().call_tool, "read_doc", {"doc_id": "nope"})


def test_structured_rejects_results_without_content():
    with pytest.raises(ValueError):
        structured(object())
