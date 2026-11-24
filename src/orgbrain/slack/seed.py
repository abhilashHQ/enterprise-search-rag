import asyncio
import hashlib
import json
import re
import sqlite3
from pathlib import Path

CHANNELS = ["incidents", "eng-runtime", "eng-releases", "eng-platform", "support", "customer-success"]
ICONS = ["bear", "fox_face", "owl", "penguin", "tiger", "koala", "frog", "octopus", "wolf", "panda_face", "rabbit", "whale"]
LINE = re.compile(r"^([A-Za-z][\w.-]*): (.*)$")


def _h(s: str) -> int:
    return int(hashlib.sha1(s.encode()).hexdigest(), 16)


def parse_thread(content: str) -> list[tuple[str, str]]:
    out: list[list[str]] = []
    for line in content.splitlines():
        m = LINE.match(line)
        if m:
            name = m.group(1)
            out.append([name if "-" in name else name.title(), m.group(2)])
        elif out:
            out[-1][1] += "\n" + line
    return [(n, t) for n, t in out]


def pick_threads(rows, per_channel: int, seed: int = 0) -> dict[str, list[str]]:
    by: dict[str, list[str]] = {}
    for doc_id, channel, content in rows:
        if 2 <= len(parse_thread(content)) <= 12:
            by.setdefault(channel, []).append(doc_id)
    return {c: sorted(ids, key=lambda d: _h(f"{seed}:{d}"))[:per_channel] for c, ids in by.items()}


async def seed(client, docstore: Path, state: Path, per_channel: int, dry_run: bool) -> dict:
    con = sqlite3.connect(f"file:{docstore.as_posix()}?mode=ro", uri=True)
    rows = con.execute(f"SELECT doc_id, title, content FROM docs WHERE source_type='slack' AND title IN "
                       f"({','.join('?' * len(CHANNELS))})", CHANNELS).fetchall()
    picked = pick_threads(rows, per_channel)
    content = {d: c for d, _, c in rows}
    done = set(json.loads(state.read_text())) if state.exists() else set()
    plan = {c: [d for d in picked.get(c, []) if d not in done] for c in CHANNELS}
    messages = sum(len(parse_thread(content[d])) for ids in plan.values() for d in ids)
    if dry_run:
        return {"channels": {c: len(v) for c, v in plan.items()}, "messages": messages, "minutes": round(messages * 1.1 / 60)}
    existing = {c["name"]: c["id"] for c in (await client.conversations_list(types="public_channel", limit=1000))["channels"]}
    for channel in CHANNELS:
        cid = existing.get(channel) or (await client.conversations_create(name=channel))["channel"]["id"]
        await client.conversations_join(channel=cid)
        for doc_id in plan[channel]:
            parent = None
            for speaker, text in parse_thread(content[doc_id]):
                text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                r = await client.chat_postMessage(channel=cid, text=text, username=speaker,
                                                  icon_emoji=f":{ICONS[_h(speaker) % len(ICONS)]}:", thread_ts=parent)
                parent = parent or r["ts"]
                await asyncio.sleep(1.1)
            done.add(doc_id)
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps(sorted(done)))
    return {"posted_threads": len(done)}
