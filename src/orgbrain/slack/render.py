import hashlib
import re
from dataclasses import dataclass

REF = re.compile(r"\[([0-9a-z]{6}(?:\s*[,;]\s*[0-9a-z]{6})*)\]")
STEPS = {"search": ("Searching", "query"), "lookup": ("Looking up", "phrase"), "find_people": ("Looking up people", "query")}


def conversation_id(channel: str, thread_ts: str) -> str:
    return hashlib.sha1(f"slack:{channel}:{thread_ts}".encode()).hexdigest()[:32]


def footnotes(text: str, citations: list[dict]) -> str:
    by_ref = {c["ref"]: c for c in citations}
    order: list[str] = []

    def number(m: re.Match) -> str:
        out = ""
        for r in re.split(r"\s*[,;]\s*", m.group(1)):
            if r not in by_ref:
                continue
            if r not in order:
                order.append(r)
            out += f"[{order.index(r) + 1}]"
        return out

    body = re.sub(r" +([.,;:])", r"\1", REF.sub(number, text)).strip()
    if not order:
        return body
    notes = "\n".join(f"[{i}] {by_ref[r]['title']} ({by_ref[r]['source']})" for i, r in enumerate(order, 1))
    return f"{body}\n\n{notes}"


def to_mrkdwn(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"^#{1,6}\s+(.+?)\s*$", r"*\1*", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"*{m.group(1) or m.group(2)}*", text)
    return re.sub(r"\[([^\]]+)\]\((\S+?)\)", r"<\2|\1>", text)


def step_line(step: dict) -> str | None:
    if step.get("kind") != "tool_call":
        return None
    if step["tool"] == "read_doc":
        return "Reading a document"
    label, arg = STEPS.get(step["tool"], (f"Using {step['tool']}", None))
    value = step.get("arguments", {}).get(arg) if arg else None
    return f"{label}: {value}" if value else label


@dataclass
class Decision:
    kind: str
    text: str = ""
    emoji: str = ""


def parse_decision(text: str) -> Decision:
    first, _, rest = text.strip().partition("\n")
    head = first.strip()
    if head.upper() == "SILENT":
        return Decision("silent")
    if head.upper().startswith("REACT"):
        return Decision("react", emoji=head.split(maxsplit=1)[1].strip(": ") if " " in head else "eyes")
    if head.upper() == "REPLY":
        return Decision("reply", rest.strip())
    return Decision("reply", text.strip())
