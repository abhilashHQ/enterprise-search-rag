"""orgbrain in Slack over Socket Mode. Answers go through the orgbrain API, so start orgbrain-api first.

  uv run --extra app orgbrain-slack run           # bot + live sync + proactive mode
  uv run --extra app orgbrain-slack seed --dry-run
  uv run --extra app orgbrain-slack seed          # posts Redwood threads into 6 channels
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time

from orgbrain.slack.render import conversation_id, footnotes, step_line, to_mrkdwn
from orgbrain.slack.sync import Names, backfill, ensure_source, event_key, first_time, index_message

MENTION = re.compile(r"^\s*<@[A-Z0-9]+>\s*")
log = logging.getLogger("orgbrain.slack")


def strip_mention(text: str) -> str:
    return MENTION.sub("", text).strip()


def memory_blocks(memory_id: int, fact: str) -> list[dict]:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"Proposed memory: {to_mrkdwn(fact)}"}},
            {"type": "actions", "block_id": f"memory:{memory_id}", "elements": [
                {"type": "button", "action_id": "memory_approve", "value": str(memory_id), "style": "primary",
                 "text": {"type": "plain_text", "text": "Approve"}},
                {"type": "button", "action_id": "memory_reject", "value": str(memory_id),
                 "text": {"type": "plain_text", "text": "Reject"}}]}]


async def answer_in_thread(client, api, channel: str, thread_ts: str, text: str, user_id: str | None,
                           min_interval: float = 1.0) -> dict | None:
    start = time.perf_counter()
    status = await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text="Looking into it...")
    log.info("status posted in %s %s after %.1fs", channel, thread_ts, time.perf_counter() - start)
    try:
        answer = await _stream_answer(client, api, channel, thread_ts, text, user_id, min_interval, status["ts"])
        if answer is not None:
            log.info("%s in %s %s after %.1fs", "answer from cache" if answer.get("from_cache") else "codex call: full turn",
                     channel, thread_ts, time.perf_counter() - start)
        return answer
    except Exception as e:
        log.exception("answer failed in %s %s", channel, thread_ts)
        await client.chat_update(channel=channel, ts=status["ts"], text=to_mrkdwn(f"I hit an error: {e}"))
        return None


async def _stream_answer(client, api, channel, thread_ts, text, user_id, min_interval, status_ts) -> dict | None:
    status = {"ts": status_ts}
    lines, last, answer, proposals, facts = [], 0.0, None, [], []
    async for name, data in api.ask(text, conversation_id(channel, thread_ts), user_id):
        if name == "step":
            if data.get("tool") == "propose_memory" and data.get("kind") == "tool_call":
                facts.append(data.get("arguments", {}).get("fact", ""))
            if "memory_id" in data:
                proposals.append((data["memory_id"], facts[-1] if facts else ""))
            if (line := step_line(data)) and line not in lines:
                lines.append(line)
                if time.monotonic() - last >= min_interval:
                    last = time.monotonic()
                    await client.chat_update(channel=channel, ts=status["ts"], text=to_mrkdwn("\n".join(lines[-4:])))
        elif name == "answer":
            answer = data
        elif name == "error":
            await client.chat_update(channel=channel, ts=status["ts"], text=to_mrkdwn(f"I hit an error: {data['message']}"))
            return None
    if answer is None:
        return None
    await client.chat_update(channel=channel, ts=status["ts"], text=to_mrkdwn(footnotes(answer["text"], answer["citations"])))
    for mid, fact in proposals:
        await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=f"Proposed memory: {to_mrkdwn(fact)}",
                                      blocks=memory_blocks(mid, fact))
    return answer


def build_app(settings, api, sessions=None, on_channel_message=None):
    from slack_bolt.async_app import AsyncApp

    app = AsyncApp(token=settings_token("ORGBRAIN_SLACK_BOT_TOKEN"))
    users = settings.slack_user_map()

    async def fresh(event) -> bool:
        return sessions is None or await first_time(sessions, event_key(event, event["channel"]))

    @app.event("app_mention")
    async def on_mention(event, client):
        if not await fresh(event):
            return
        await answer_in_thread(client, api, event["channel"], event.get("thread_ts") or event["ts"],
                               strip_mention(event["text"]), users.get(event.get("user")))

    @app.event("message")
    async def on_message(event, client, context):
        if event.get("bot_id") or event.get("subtype"):
            return
        mentioned = f"<@{context['bot_user_id']}>" in event.get("text", "")
        if event.get("channel_type") != "im" and (mentioned or on_channel_message is None):
            return
        if not await fresh(event):
            return
        if event.get("channel_type") == "im":
            await answer_in_thread(client, api, event["channel"], event.get("thread_ts") or event["ts"],
                                   event["text"], users.get(event.get("user")))
        else:
            await on_channel_message(event, client)

    async def decide(ack, body, client, action: str):
        await ack()
        mid, who = int(body["actions"][0]["value"]), users.get(body["user"]["id"])
        if who is None:
            msg = "Only mapped admins can decide on memories. Ask the workspace owner to map your Slack account."
        else:
            code, data = await api.decide(mid, action, who)
            msg = {200: f"Memory {mid} {data.get('status', action)} by {who}."}.get(code, f"Not done: {data.get('error')}")
        await client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text=to_mrkdwn(msg), blocks=[])

    @app.action("memory_approve")
    async def approve(ack, body, client):
        await decide(ack, body, client, "approve")

    @app.action("memory_reject")
    async def reject(ack, body, client):
        await decide(ack, body, client, "reject")

    return app


def settings_token(name: str) -> str:
    token = os.environ.get(name)
    if not token:
        raise SystemExit(f"{name} is not set; see docs/slack-setup.md")
    return token


def sessions_for(settings):
    from sqlalchemy.ext.asyncio import create_async_engine

    from orgbrain.db import ConversationStore

    return ConversationStore(create_async_engine(settings.database_url)).sessions


def web_client():
    from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
    from slack_sdk.web.async_client import AsyncWebClient

    return AsyncWebClient(token=settings_token("ORGBRAIN_SLACK_BOT_TOKEN"),
                          retry_handlers=[AsyncRateLimitErrorRetryHandler(max_retry_count=5)])


async def run(settings) -> None:
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    from orgbrain.slack.api_client import OrgbrainApi

    from collections import deque

    from redis.asyncio import Redis

    from entsearch.data import ROOT
    from orgbrain.runtime.codex import CodexConfig, CodexRuntime
    from orgbrain.runtime.events import Message
    from orgbrain.slack.proactive import Budget, consider, parse_triage

    sessions, names, index_lock = sessions_for(settings), Names(), asyncio.Lock()
    await ensure_source(sessions)
    api, users = OrgbrainApi(settings.api_url), settings.slack_user_map()
    budget = Budget(Redis.from_url(settings.redis_url), int(settings.proactive_per_hour))
    triage_rt = CodexRuntime(CodexConfig(model=settings.triage_model, effort="low", mcp_url=None,
                                         workdir=ROOT / "data/codex_work"), instructions="")
    recent: dict[str, deque] = {}
    turn_lock = asyncio.Lock()

    async def triage(prompt: str) -> bool:
        start, text = time.perf_counter(), ""
        async for ev in triage_rt.run(prompt):
            if isinstance(ev, Message):
                text = ev.text
        log.info("codex call: triage %s in %.1fs", text.strip()[:40] or "(empty)", time.perf_counter() - start)
        return parse_triage(text)

    async def on_channel_message(event, client):
        thread_ts = event.get("thread_ts") or event["ts"]
        speaker = await names.user(client, event["user"])
        channel_name = await names.channel(client, event["channel"])
        async with index_lock:
            await index_message(sessions, event["channel"], channel_name, thread_ts, speaker, event["text"])
        log.info("indexed %s in #%s", thread_ts, channel_name)
        lines = recent.setdefault(event["channel"], deque(maxlen=20))
        before = list(lines)
        lines.append(f"{speaker}: {event['text']}")
        if turn_lock.locked():
            log.info("proactive busy, dropped %s in #%s", event["ts"], channel_name)
            return
        async with turn_lock:
            start = time.perf_counter()
            try:
                outcome = await consider(event, client, api, triage, budget, channel_name, before, users.get(event["user"]))
            except Exception:
                log.exception("proactive failed on %s in #%s", event["ts"], channel_name)
                return
            log.info("proactive %s on %s in #%s in %.1fs", outcome, event["ts"], channel_name, time.perf_counter() - start)
            if outcome not in ("skipped", "over_budget"):
                log.info("codex call: full proactive turn (%s)", outcome)

    app = build_app(settings, api, sessions, on_channel_message)
    handler = AsyncSocketModeHandler(app, settings_token("ORGBRAIN_SLACK_APP_TOKEN"))
    await handler.connect_async()
    log.info("connected over Socket Mode")
    async with index_lock:
        log.info("backfill indexed %d human messages", await backfill(app.client, sessions, names))
    await asyncio.Event().wait()


def main() -> None:
    from orgbrain.config import Settings

    p = argparse.ArgumentParser(prog="orgbrain-slack", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("backfill")
    sp = sub.add_parser("seed")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--per-channel", type=int, default=30)
    up = sub.add_parser("unseed", help="delete the seeded posts in the seed channels")
    up.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.from_env()
    if a.cmd == "run":
        asyncio.run(run(settings))
    elif a.cmd == "backfill":
        print(asyncio.run(backfill(web_client(), sessions_for(settings))), "human messages indexed")
    elif a.cmd == "seed":
        from entsearch.data import ROOT
        from orgbrain.slack.seed import seed

        client = None if a.dry_run else web_client()
        print(json.dumps(asyncio.run(seed(client, settings.docstore_path, ROOT / "data/orgbrain/slack_seed.json",
                                          a.per_channel, a.dry_run)), indent=2))
    elif a.cmd == "unseed":
        from orgbrain.slack.seed import unseed

        print(json.dumps(asyncio.run(unseed(web_client(), a.dry_run)), indent=2))


if __name__ == "__main__":
    main()
