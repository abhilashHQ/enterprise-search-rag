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


def collect_people(tool_results: list[dict]) -> dict[str, str]:
    """id -> name of every person find_people returned (rows with an id and a name, and no document ref)."""
    return {p["id"]: p["name"] for r in tool_results for p in r.get("results", [])
            if "ref" not in p and "id" in p and "name" in p}


def finalize(text: str, hits: dict[str, dict], people: dict[str, str] | None = None) -> Answer:
    """An answer is grounded by a resolved citation or by naming a person the directory returned; otherwise it counts
    as abstained."""
    refs = cited_refs(text)
    citations = [Citation(r, **hits[r]) for r in refs if r in hits]
    named = any(name.lower() in text.lower() for name in (people or {}).values())
    return Answer(text=text, citations=citations, abstained=not citations and not named,
                  unknown_refs=[r for r in refs if r not in hits])
