from pathlib import Path

from orgbrain.sources import SOURCE_HELP

CONSTITUTION = Path(__file__).with_name("constitution.md")


def instructions(company: str = "Redwood Inference", path: Path | None = None) -> str:
    text = (path or CONSTITUTION).read_text(encoding="utf8")
    if "{company}" not in text:
        raise ValueError(f"{path or CONSTITUTION} has no {{company}} placeholder")
    sources = "\n".join(f"- {s.value}: {h}" for s, h in SOURCE_HELP.items())
    tools = ("\n\n## Your tools\n\n`search` can be limited to one or more of these sources when the question clearly "
             f"points at them:\n\n{sources}\n")
    return text.replace("{company}", company) + tools
