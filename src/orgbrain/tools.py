from dataclasses import asdict

from orgbrain.refs import ref
from orgbrain.search import SearchBackend
from orgbrain.sources import SOURCE_HELP, Source

MAX_K = 20
DOC_CHARS = 12000
HINT = ("Cite results as [ref] right after each claim. If these look unrelated to the question, search again with other "
        "words or without the sources filter. Use read_doc(doc_id) when a snippet is not enough.")


def search_tool(backend: SearchBackend, query: str, sources: list[str] | None = None, k: int = 10) -> dict:
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}")
    valid = {s.value for s in Source}
    bad = [s for s in sources or [] if s not in valid]
    if bad:
        raise ValueError(f"unknown source {bad}; valid sources: {sorted(valid)}")
    hits = backend.search(query, list(sources) if sources else None, k)
    return {"query": query, "sources": list(sources) if sources else "all", "results": [asdict(h) for h in hits],
            "hint": HINT}


def read_doc_tool(backend: SearchBackend, doc_id: str) -> dict:
    doc = backend.read_doc(doc_id)
    if doc is None:
        raise LookupError(f"unknown doc_id {doc_id!r}")
    return {"ref": ref(doc.doc_id), "doc_id": doc.doc_id, "source": doc.source, "title": doc.title,
            "content": doc.content[:DOC_CHARS], "truncated": len(doc.content) > DOC_CHARS}


_SOURCES_DOC = "; ".join(f"{s.value}: {h}" for s, h in SOURCE_HELP.items())

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "search",
        "description": "Search the company's documents. Returns the top k results with ref, doc_id, source, title and "
                       "snippet. Filter by sources only when the question clearly points at one kind of system. "
                       f"Sources: {_SOURCES_DOC}.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to look for, in plain words."},
            "sources": {"type": "array", "items": {"type": "string", "enum": [s.value for s in Source]},
                        "description": "Only search these sources. Omit to search everything."},
            "k": {"type": "integer", "minimum": 1, "maximum": MAX_K, "default": 10},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "read_doc",
        "description": "Full text of one document by doc_id, from a search result.",
        "parameters": {"type": "object", "properties": {"doc_id": {"type": "string"}}, "required": ["doc_id"]},
    }},
]
