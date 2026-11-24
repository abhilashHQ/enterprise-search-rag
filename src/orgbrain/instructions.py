from pathlib import Path

from orgbrain.sources import SOURCE_HELP

CONSTITUTION = Path(__file__).with_name("constitution.md")


def instructions(company: str = "Redwood Inference", path: Path | None = None) -> str:
    text = (path or CONSTITUTION).read_text(encoding="utf8")
    if "{company}" not in text:
        raise ValueError(f"{path or CONSTITUTION} has no {{company}} placeholder")
    sources = "\n".join(f"- {s.value}: {h}" for s, h in SOURCE_HELP.items())
    tools = ("\n\n## Your tools\n\n`search` finds documents by meaning and keywords; page past the first results with "
             "`offset`. `lookup` finds documents containing an exact phrase. `read_doc` reads a document 12,000 characters "
             "at a time; follow `next_offset` to the end of a long one. `search` and `lookup` can be limited to one or "
             f"more of these sources when the question clearly points at them:\n\n{sources}\n\n"
             "`find_people` finds colleagues by name, role, team or topic; roles and topics are inferred from the record. "
             "`propose_memory` proposes a fact for an admin to approve; pass the teammate's id from the `(Teammate: ...)` "
             "line as `proposed_by`.\n")
    return text.replace("{company}", company) + tools
