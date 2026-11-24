from types import SimpleNamespace

import pytest

from orgbrain.refs import ref
from orgbrain.search import Doc, Hit, LocalSearch
from orgbrain.tools import DOC_CHARS, TOOL_SPECS, lookup_tool, read_doc_tool, search_tool


class FakeBackend:
    def __init__(self):
        self.calls = []

    def search(self, query, sources, k, offset=0):
        self.calls.append((query, sources, k, offset))
        return [Hit(ref(f"d{i}"), f"d{i}", "jira", f"T{i}", "snip", 0.9) for i in range(offset, offset + k)]

    def lookup(self, phrase, sources, k):
        self.calls.append((phrase, sources, k))
        return [Hit(ref("d9"), "d9", "linear", "T9", f"... {phrase} ...", None)][:k]

    def read_doc(self, doc_id):
        return Doc(doc_id, "confluence", "Runbook", "x" * (DOC_CHARS + 5)) if doc_id == "d1" else None


def test_search_tool_passes_filter_and_shapes_results():
    b = FakeBackend()
    out = search_tool(b, "rollback", sources=["jira"], k=2)
    assert b.calls == [("rollback", ["jira"], 2, 0)]
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


def test_search_tool_pages_with_offset():
    out = search_tool(FakeBackend(), "q", k=2, offset=10)
    assert [r["doc_id"] for r in out["results"]] == ["d10", "d11"] and out["offset"] == 10


@pytest.mark.parametrize("offset", [-1, 91])
def test_search_tool_rejects_offset_past_depth(offset):
    with pytest.raises(ValueError, match="offset"):
        search_tool(FakeBackend(), "q", k=10, offset=offset)


def test_lookup_tool_passes_phrase_and_filter():
    b = FakeBackend()
    out = lookup_tool(b, "TKT-4471", sources=["linear"], k=3)
    assert b.calls == [("TKT-4471", ["linear"], 3)]
    assert out["phrase"] == "TKT-4471" and out["results"][0]["doc_id"] == "d9"


def test_lookup_tool_rejects_empty_phrase():
    with pytest.raises(ValueError, match="empty"):
        lookup_tool(FakeBackend(), "  ")


def test_read_doc_tool_pages_through_a_long_doc():
    first = read_doc_tool(FakeBackend(), "d1")
    assert first["ref"] == ref("d1") and len(first["content"]) == DOC_CHARS and first["next_offset"] == DOC_CHARS
    rest = read_doc_tool(FakeBackend(), "d1", offset=first["next_offset"])
    assert rest["content"] == "x" * 5 and rest["next_offset"] is None and rest["total_chars"] == DOC_CHARS + 5


def test_read_doc_tool_rejects_offset_past_end():
    with pytest.raises(ValueError, match="offset"):
        read_doc_tool(FakeBackend(), "d1", offset=DOC_CHARS + 5)


def test_read_doc_tool_unknown_id():
    with pytest.raises(LookupError):
        read_doc_tool(FakeBackend(), "nope")


def test_local_search_maps_pipeline_hits():
    hit = SimpleNamespace(doc_id="d7", source="slack", title="eng", snippet="s", rerank_score=None, fused_score=0.03)
    pipeline = SimpleNamespace(
        search=lambda query, k, sources: SimpleNamespace(hits=[hit] * k),
        get_document=lambda doc_id: {"doc_id": doc_id, "source": "slack", "title": "eng", "content": "c"},
    )
    s = LocalSearch(pipeline)
    assert s.search("q", ["slack"], 1) == [Hit(ref("d7"), "d7", "slack", "eng", "s", 0.03)]
    assert len(s.search("q", None, 2, offset=3)) == 2
    with pytest.raises(NotImplementedError):
        s.lookup("x", None, 1)
    assert s.read_doc("d7") == Doc("d7", "slack", "eng", "c")


def test_tool_specs_name_all_tools_and_enum_sources():
    names = [t["function"]["name"] for t in TOOL_SPECS]
    assert names == ["search", "lookup", "read_doc"]
    enum = TOOL_SPECS[0]["function"]["parameters"]["properties"]["sources"]["items"]["enum"]
    assert "memory" in enum and "google_drive" in enum
