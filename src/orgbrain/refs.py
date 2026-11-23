import hashlib
import re

REF_LEN = 6
_CITE = re.compile(r"\[([0-9a-f]{6}(?:\s*[,;]\s*[0-9a-f]{6})*)\]")


def ref(doc_id: str) -> str:
    return hashlib.sha1(doc_id.encode()).hexdigest()[:REF_LEN]


def cited_refs(text: str) -> list[str]:
    found = [r for m in _CITE.finditer(text) for r in re.split(r"\s*[,;]\s*", m.group(1))]
    return list(dict.fromkeys(found))
