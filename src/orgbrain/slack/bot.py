"""orgbrain in Slack over Socket Mode. Answers go through the orgbrain API, so start orgbrain-api first.

  uv run --extra app orgbrain-slack run           # bot + live sync + proactive mode
  uv run --extra app orgbrain-slack seed --dry-run
  uv run --extra app orgbrain-slack seed          # posts Redwood threads into 6 channels
"""

import argparse
import asyncio
import logging
import os
import re
import sys
import time

from orgbrain.slack.render import conversation_id, footnotes, step_line, to_mrkdwn

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
    status = await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text="Looking into it...")
    try:
        return await _stream_answer(client, api, channel, thread_ts, text, user_id, min_interval, status["ts"])
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

    @app.event("app_mention")
    async def on_mention(event, client):
        await answer_in_thread(client, api, event["channel"], event.get("thread_ts") or event["ts"],
                               strip_mention(event["text"]), users.get(event.get("user")))

    @app.event("message")
    async def on_message(event, client, context):
        if event.get("bot_id") or event.get("subtype"):
            return
        if event.get("channel_type") == "im":
            await answer_in_thread(client, api, event["channel"], event.get("thread_ts") or event["ts"],
                                   event["text"], users.get(event.get("user")))
        elif on_channel_message and f"<@{context['bot_user_id']}>" not in event.get("text", ""):
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


async def run(settings) -> None:
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    from orgbrain.slack.api_client import OrgbrainApi

    app = build_app(settings, OrgbrainApi(settings.api_url))
    await AsyncSocketModeHandler(app, settings_token("ORGBRAIN_SLACK_APP_TOKEN")).start_async()


def main() -> None:
    from orgbrain.config import Settings

    p = argparse.ArgumentParser(prog="orgbrain-slack", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.from_env()
    if a.cmd == "run":
        asyncio.run(run(settings))


if __name__ == "__main__":
    main()
