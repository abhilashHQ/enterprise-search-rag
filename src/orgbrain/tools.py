from dataclasses import asdict

from orgbrain.refs import ref
from orgbrain.search import SearchBackend
from orgbrain.sources import SOURCE_HELP, Source

MAX_K = 20
MAX_DEPTH = 100
DOC_CHARS = 12000
HINT = ("Cite results as [ref] right after each claim. If these look unrelated to the question, search again with other "
        "words or without the sources filter. Use offset to see results past the first page, lookup for an exact name, "
        "number or phrase, and read_doc(doc_id) when a snippet is not enough.")


def _check(k: int, sources: list[str] | None) -> list[str] | None:
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}")
    valid = {s.value for s in Source}
    bad = [s for s in sources or [] if s not in valid]
    if bad:
        raise ValueError(f"unknown source {bad}; valid sources: {sorted(valid)}")
    return list(sources) if sources else None


def search_tool(backend: SearchBackend, query: str, sources: list[str] | None = None, k: int = 10,
                offset: int = 0) -> dict:
    sources = _check(k, sources)
    if not 0 <= offset <= MAX_DEPTH - k:
        raise ValueError(f"offset must be between 0 and {MAX_DEPTH} - k")
    hits = backend.search(query, sources, k, offset)
    return {"query": query, "sources": sources or "all", "offset": offset, "results": [asdict(h) for h in hits],
            "hint": HINT}


def lookup_tool(backend: SearchBackend, phrase: str, sources: list[str] | None = None, k: int = 10) -> dict:
    sources = _check(k, sources)
    if not phrase.strip():
        raise ValueError("phrase is empty")
    hits = backend.lookup(phrase, sources, k)
    return {"phrase": phrase, "sources": sources or "all", "results": [asdict(h) for h in hits], "hint": HINT}


def read_doc_tool(backend: SearchBackend, doc_id: str, offset: int = 0) -> dict:
    doc = backend.read_doc(doc_id)
    if doc is None:
        raise LookupError(f"unknown doc_id {doc_id!r}")
    if not 0 <= offset < max(len(doc.content), 1):
        raise ValueError(f"offset must be between 0 and {len(doc.content) - 1}")
    end = offset + DOC_CHARS
    return {"ref": ref(doc.doc_id), "doc_id": doc.doc_id, "source": doc.source, "title": doc.title,
            "content": doc.content[offset:end], "offset": offset, "total_chars": len(doc.content),
            "next_offset": end if end < len(doc.content) else None}


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
            "offset": {"type": "integer", "minimum": 0, "default": 0,
                       "description": "Skip this many results, to page past the first ones (up to 100 deep)."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "lookup",
        "description": "Documents whose title or text contains an exact phrase (case-insensitive): a ticket key, a "
                       "metric or config name, a customer, a person, a date as written. Best for specifics that plain "
                       "search ranks poorly.",
        "parameters": {"type": "object", "properties": {
            "phrase": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string", "enum": [s.value for s in Source]}},
            "k": {"type": "integer", "minimum": 1, "maximum": MAX_K, "default": 10},
        }, "required": ["phrase"]},
    }},
    {"type": "function", "function": {
        "name": "read_doc",
        "description": "Text of one document by doc_id, 12,000 characters at a time. If next_offset is set, call "
                       "again with offset=next_offset for the rest.",
        "parameters": {"type": "object", "properties": {
            "doc_id": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        }, "required": ["doc_id"]},
    }},
]
