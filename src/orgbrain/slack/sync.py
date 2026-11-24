import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from orgbrain.db import ConnectorSource, Outbox, SlackEvent, SourceFile, enqueue


async def first_time(sessions, event_id: str) -> bool:
    try:
        async with sessions.begin() as s:
            s.add(SlackEvent(event_id=event_id))
        return True
    except IntegrityError:
        return False


def event_key(message: dict, channel_id: str) -> str:
    return message.get("client_msg_id") or message["ts"] + channel_id


def thread_doc_id(channel_id: str, thread_ts: str) -> str:
    return f"slack-live:{channel_id}:{thread_ts}"


async def ensure_source(sessions) -> None:
    async with sessions.begin() as s:
        if await s.get(ConnectorSource, "slack") is None:
            s.add(ConnectorSource(id="slack", kind="slack", config={}))


async def index_message(sessions, channel_id: str, channel_name: str, thread_ts: str, speaker: str, text: str) -> None:
    doc_id = thread_doc_id(channel_id, thread_ts)
    async with sessions.begin() as s:
        prev = (await s.execute(select(Outbox).where(Outbox.doc_id == doc_id).order_by(Outbox.id.desc()).limit(1))).scalar()
        lines = prev.payload["content"].split("\n") if prev else []
        lines.append(f"{speaker}: {text}")
        await s.merge(SourceFile(source_id="slack", rel_path=doc_id, doc_id=doc_id, sha256=""))
        enqueue(s, "upsert", doc_id, {"source": "slack", "title": channel_name, "content": "\n".join(lines)})


class Names:
    def __init__(self):
        self.users: dict[str, str] = {}
        self.channels: dict[str, str] = {}

    async def user(self, client, user_id: str) -> str:
        if user_id not in self.users:
            u = (await client.users_info(user=user_id))["user"]
            self.users[user_id] = u.get("real_name") or u.get("profile", {}).get("display_name") or u.get("name") or user_id
        return self.users[user_id]

    async def channel(self, client, channel_id: str) -> str:
        if channel_id not in self.channels:
            self.channels[channel_id] = (await client.conversations_info(channel=channel_id))["channel"]["name"]
        return self.channels[channel_id]


def is_human(m: dict) -> bool:
    return not m.get("bot_id") and not m.get("subtype") and "user" in m


async def _pages(call, key: str, pause: float, **kw):
    cursor = None
    while True:
        r = await call(**kw, limit=200, **({"cursor": cursor} if cursor else {}))
        for item in r[key]:
            yield item
        cursor = (r.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            return
        await asyncio.sleep(pause)


async def backfill(client, sessions, names: Names | None = None, pause: float = 1.2) -> int:
    """Index human messages in every public channel the bot is a member of. Messages already seen live are skipped."""
    names = names or Names()
    await ensure_source(sessions)
    mention = f"<@{(await client.auth_test())['user_id']}>"
    count = 0
    async for ch in _pages(client.conversations_list, "channels", pause, types="public_channel", exclude_archived=True):
        if not ch.get("is_member"):
            continue
        names.channels[ch["id"]] = ch["name"]
        messages = []
        async for m in _pages(client.conversations_history, "messages", pause, channel=ch["id"]):
            messages.append(m)
            if m.get("reply_count"):
                await asyncio.sleep(pause)
                async for r in _pages(client.conversations_replies, "messages", pause, channel=ch["id"], ts=m["ts"]):
                    if r["ts"] != m["ts"]:
                        messages.append(r)
        await asyncio.sleep(pause)
        for m in sorted(messages, key=lambda m: float(m["ts"])):
            if not is_human(m) or mention in m.get("text", "") or not await first_time(sessions, event_key(m, ch["id"])):
                continue
            await index_message(sessions, ch["id"], ch["name"], m.get("thread_ts") or m["ts"],
                                await names.user(client, m["user"]), m["text"])
            count += 1
    return count
