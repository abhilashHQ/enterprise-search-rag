import asyncio
import collections
import hashlib
import json
import re
import sqlite3
from pathlib import Path

CHANNELS = ["incidents", "eng-runtime", "eng-releases", "eng-platform", "support", "customer-success"]
ICONS = ["bear", "fox_face", "owl", "penguin", "tiger", "koala", "frog", "octopus", "wolf", "panda_face", "rabbit", "whale"]
SPEAKER = re.compile(r"^(?P<name>[a-z][\w'-]*(?:\.[a-z0-9_-]+)+|[A-Za-z][\w'-]*(?:[ .][A-Z][\w'-]*\.?)?)(?: \((?P<team>[^()]{1,40})\))?: (?P<text>.*)$")


def _h(s: str) -> int:
    return int(hashlib.sha1(s.encode()).hexdigest(), 16)


def _speaker_lines(content: str):
    fence, fences_balance = False, content.count("```") % 2 == 0
    for line in content.splitlines():
        yield line, None if fence else SPEAKER.match(line)
        if fences_balance and line.count("```") % 2:
            fence = not fence


def parse_thread(content: str, known: set[str] | None = None) -> list[tuple[str, str]]:
    """Split a corpus thread into (display name, text) messages. A `Name:` or `Name (team):` line outside a code fence
    starts a message. With `known` (lowercased names that start some Slack thread), a name must also be the thread's
    first speaker, appear twice, be known, or end in "bot"; other `Label:` lines stay in the text."""
    lines = list(_speaker_lines(content))
    names = [m["name"] for _, m in lines if m]
    count = collections.Counter(names)

    def speaks(n: str) -> bool:
        return known is None or n == names[0] or count[n] >= 2 or n.lower() in known or n.lower().endswith("bot")

    out: list[list[str]] = []
    for line, m in lines:
        if m and speaks(m["name"]):
            name = m["name"].title() if m["name"].isalpha() and m["name"].islower() else m["name"]
            out.append([f"{name} ({m['team']})" if m["team"] else name, m["text"]])
        elif out:
            out[-1][1] += "\n" + line
    return [(n, t.strip()) for n, t in out]


def slack_starters(con) -> set[str]:
    out = set()
    for (head,) in con.execute("SELECT substr(content, 1, 120) FROM docs WHERE source_type='slack'"):
        if m := SPEAKER.match(head.split("\n", 1)[0]):
            out.add(m["name"].lower())
    return out


def pick_threads(rows, per_channel: int, seed: int = 0, known: set[str] | None = None) -> dict[str, list[str]]:
    by: dict[str, list[str]] = {}
    for doc_id, channel, content in rows:
        if 2 <= len(parse_thread(content, known)) <= 12:
            by.setdefault(channel, []).append(doc_id)
    return {c: sorted(ids, key=lambda d: _h(f"{seed}:{d}"))[:per_channel] for c, ids in by.items()}


async def seed(client, docstore: Path, state: Path, per_channel: int, dry_run: bool) -> dict:
    con = sqlite3.connect(f"file:{docstore.as_posix()}?mode=ro", uri=True)
    rows = con.execute(f"SELECT doc_id, title, content FROM docs WHERE source_type='slack' AND title IN "
                       f"({','.join('?' * len(CHANNELS))})", CHANNELS).fetchall()
    known = slack_starters(con)
    picked = pick_threads(rows, per_channel, known=known)
    content = {d: c for d, _, c in rows}
    done = set(json.loads(state.read_text())) if state.exists() else set()
    plan = {c: [d for d in picked.get(c, []) if d not in done] for c in CHANNELS}
    messages = sum(len(parse_thread(content[d], known)) for ids in plan.values() for d in ids)
    if dry_run:
        return {"channels": {c: len(v) for c, v in plan.items()}, "messages": messages, "minutes": round(messages * 1.1 / 60)}
    existing = {c["name"]: c["id"] for c in (await client.conversations_list(types="public_channel", limit=1000))["channels"]}
    for channel in CHANNELS:
        cid = existing.get(channel) or (await client.conversations_create(name=channel))["channel"]["id"]
        await client.conversations_join(channel=cid)
        for doc_id in plan[channel]:
            parent = None
            for speaker, text in parse_thread(content[doc_id], known):
                text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                r = await client.chat_postMessage(channel=cid, text=text, username=speaker,
                                                  icon_emoji=f":{ICONS[_h(speaker) % len(ICONS)]}:", thread_ts=parent)
                parent = parent or r["ts"]
                await asyncio.sleep(1.1)
            done.add(doc_id)
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps(sorted(done)))
    return {"posted_threads": len(done)}


async def unseed(client, dry_run: bool) -> dict:
    """Delete this app's seeded posts (bot messages with a username override) in the seed channels. Messages people
    wrote and orgbrain's own answers stay."""
    from orgbrain.slack.sync import _pages

    bot_id = (await client.auth_test())["bot_id"]

    def seeded(m: dict) -> bool:
        return m.get("bot_id") == bot_id and bool(m.get("username"))

    counts = {}
    for ch in (await client.conversations_list(types="public_channel", limit=1000))["channels"]:
        if ch["name"] not in CHANNELS:
            continue
        doomed = []
        async for m in _pages(client.conversations_history, "messages", 1.2, channel=ch["id"]):
            if m.get("reply_count"):
                await asyncio.sleep(1.2)
                async for r in _pages(client.conversations_replies, "messages", 1.2, channel=ch["id"], ts=m["ts"]):
                    if r["ts"] != m["ts"] and seeded(r):
                        doomed.append(r["ts"])
            if seeded(m):
                doomed.append(m["ts"])
        counts[ch["name"]] = len(doomed)
        if not dry_run:
            for ts in doomed:
                await client.chat_delete(channel=ch["id"], ts=ts)
                await asyncio.sleep(1.2)
    return counts
