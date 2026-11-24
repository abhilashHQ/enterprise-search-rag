from concurrent.futures import Future

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from orgbrain.mcp_server import build_server, structured
from orgbrain.refs import ref
from orgbrain.search import Doc, Hit


class FakeBackend:
    def search(self, query, sources, k, offset=0):
        return [Hit(ref("d1"), "d1", (sources or ["jira"])[0], "T", "s", 1.0)][:k]

    def lookup(self, phrase, sources, k):
        return [Hit(ref("d1"), "d1", "jira", "T", phrase, None)][:k]

    def read_doc(self, doc_id):
        return Doc("d1", "jira", "T", "body") if doc_id == "d1" else None


def server():
    f: Future = Future()
    f.set_result(FakeBackend())
    return build_server(f)


def test_lists_search_lookup_and_read_doc_with_source_enum():
    tools = anyio.run(server().list_tools)
    assert {t.name for t in tools} == {"search", "lookup", "read_doc"}
    search = next(t for t in tools if t.name == "search")
    assert "google_drive" in search.model_dump_json() and "memory" in search.model_dump_json()


def test_search_returns_structured_results():
    r = anyio.run(server().call_tool, "search", {"query": "x", "sources": ["slack"], "k": 1})
    out = structured(r)
    assert out["results"][0]["source"] == "slack" and out["results"][0]["ref"] == ref("d1")


def test_lookup_returns_structured_results():
    out = structured(anyio.run(server().call_tool, "lookup", {"phrase": "TKT-1", "k": 1}))
    assert out["results"][0]["snippet"] == "TKT-1"


def test_read_doc_pages():
    out = structured(anyio.run(server().call_tool, "read_doc", {"doc_id": "d1", "offset": 2}))
    assert out["content"] == "dy" and out["next_offset"] is None


def test_unknown_doc_is_a_tool_error():
    with pytest.raises(ToolError, match="unknown doc_id"):
        anyio.run(server().call_tool, "read_doc", {"doc_id": "nope"})


def test_structured_rejects_results_without_content():
    with pytest.raises(ValueError):
        structured(object())


def test_make_backend_rejects_unknown_name():
    from pathlib import Path

    from orgbrain.mcp_server import make_backend

    with pytest.raises(ValueError, match="backend"):
        make_backend("opensearch", Path("."), "fp16", "cpu")


class FakeMemories:
    def __init__(self):
        self.proposed = []

    async def propose(self, text, proposed_by=None, conversation_id=None):
        self.proposed.append((text, proposed_by, conversation_id))
        return 7


def test_propose_memory_writes_a_pending_proposal():
    from orgbrain.memory import AppStores

    f: Future = Future()
    f.set_result(FakeBackend())
    mem = FakeMemories()
    srv = build_server(f, AppStores(mem))
    out = structured(anyio.run(srv.call_tool, "propose_memory", {"fact": "Freeze starts Dec 15", "proposed_by": "sam",
                                                                  "conversation_id": "c" * 32}))
    assert out["id"] == 7 and out["status"] == "pending"
    assert mem.proposed == [("Freeze starts Dec 15", "sam", "c" * 32)]


class FakePeople:
    async def find(self, query, k=10):
        return [{"id": "markus.klein", "name": "Markus Klein", "role": "CSM"}][:k]


def test_find_people_returns_matches():
    from orgbrain.memory import AppStores

    f: Future = Future()
    f.set_result(FakeBackend())
    srv = build_server(f, AppStores(FakeMemories(), FakePeople()))
    out = structured(anyio.run(srv.call_tool, "find_people", {"query": "renewals", "k": 50}))
    assert out["query"] == "renewals" and [p["id"] for p in out["results"]] == ["markus.klein"]
