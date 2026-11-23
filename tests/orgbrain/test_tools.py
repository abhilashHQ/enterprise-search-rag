from types import SimpleNamespace

import pytest

from orgbrain.refs import ref
from orgbrain.search import Doc, Hit, LocalSearch
from orgbrain.tools import DOC_CHARS, TOOL_SPECS, read_doc_tool, search_tool


class FakeBackend:
    def __init__(self):
        self.calls = []

    def search(self, query, sources, k):
        self.calls.append((query, sources, k))
        return [Hit(ref(f"d{i}"), f"d{i}", "jira", f"T{i}", "snip", 0.9) for i in range(k)]

    def read_doc(self, doc_id):
        return Doc(doc_id, "confluence", "Runbook", "x" * (DOC_CHARS + 5)) if doc_id == "d1" else None


def test_search_tool_passes_filter_and_shapes_results():
    b = FakeBackend()
    out = search_tool(b, "rollback", sources=["jira"], k=2)
    assert b.calls == [("rollback", ["jira"], 2)]
    assert out["sources"] == ["jira"] and len(out["results"]) == 2
    assert out["results"][0] == {"ref": ref("d0"), "doc_id": "d0", "source": "jira", "title": "T0", "snippet": "snip", "score": 0.9}
    assert "[ref]" in out["hint"]


def test_search_tool_empty_filter_means_all_sources():
    b = FakeBackend()
    assert search_tool(b, "q", sources=[], k=1)["sources"] == "all"
    assert b.calls[0][1] is None


@pytest.mark.parametrize("k", [0, 21])
def test_search_tool_rejects_bad_k(k):
    with pytest.raises(ValueError, match="k must be"):
        search_tool(FakeBackend(), "q", k=k)


def test_search_tool_rejects_unknown_source():
    with pytest.raises(ValueError, match="unknown source"):
        search_tool(FakeBackend(), "q", sources=["notion"])


def test_read_doc_tool_truncates_and_carries_ref():
    out = read_doc_tool(FakeBackend(), "d1")
    assert out["ref"] == ref("d1") and out["truncated"] is True and len(out["content"]) == DOC_CHARS


def test_read_doc_tool_unknown_id():
    with pytest.raises(LookupError):
        read_doc_tool(FakeBackend(), "nope")


def test_local_search_maps_pipeline_hits():
    hit = SimpleNamespace(doc_id="d7", source="slack", title="eng", snippet="s", rerank_score=None, fused_score=0.03)
    pipeline = SimpleNamespace(
        search=lambda query, k, sources: SimpleNamespace(hits=[hit]),
        get_document=lambda doc_id: {"doc_id": doc_id, "source": "slack", "title": "eng", "content": "c"},
    )
    s = LocalSearch(pipeline)
    assert s.search("q", ["slack"], 1) == [Hit(ref("d7"), "d7", "slack", "eng", "s", 0.03)]
    assert s.read_doc("d7") == Doc("d7", "slack", "eng", "c")


def test_tool_specs_name_both_tools_and_enum_sources():
    names = [t["function"]["name"] for t in TOOL_SPECS]
    assert names == ["search", "read_doc"]
    enum = TOOL_SPECS[0]["function"]["parameters"]["properties"]["sources"]["items"]["enum"]
    assert "memory" in enum and "google_drive" in enum
