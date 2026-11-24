from dataclasses import dataclass, field

from orgbrain.refs import cited_refs


@dataclass
class Citation:
    ref: str
    doc_id: str
    source: str
    title: str


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    abstained: bool
    unknown_refs: list[str] = field(default_factory=list)


def collect_hits(tool_results: list[dict]) -> dict[str, dict]:
    hits: dict[str, dict] = {}
    for r in tool_results:
        rows = r.get("results", []) + ([r] if "ref" in r else [])
        for h in (h for h in rows if "ref" in h):
            hits.setdefault(h["ref"], {"doc_id": h["doc_id"], "source": h["source"], "title": h["title"]})
    return hits


def finalize(text: str, hits: dict[str, dict]) -> Answer:
    refs = cited_refs(text)
    citations = [Citation(r, **hits[r]) for r in refs if r in hits]
    return Answer(text=text, citations=citations, abstained=not citations, unknown_refs=[r for r in refs if r not in hits])
