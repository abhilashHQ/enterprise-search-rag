import logging
import time

from orgbrain.slack.render import conversation_id, footnotes, parse_decision, to_mrkdwn

log = logging.getLogger("orgbrain.slack.proactive")

TRIAGE_PROMPT = """You watch a company Slack channel for an assistant that knows the company's documents. Decide if this \
message might need the assistant: a question the company record could answer, a claim that may contradict a past \
decision, or work that may already exist. Social chat, thanks, jokes and messages already answered need nothing.
Reply with one word, YES or NO.

Recent messages in #{channel}:
{recent}

New message:
{text}"""


def parse_triage(text: str) -> bool:
    return text.strip().upper().startswith("YES")


class Budget:
    def __init__(self, redis, per_hour: int, clock=time.time):
        self.redis, self.per_hour, self.clock = redis, per_hour, clock

    async def take(self) -> bool:
        key = f"orgbrain:proactive:{int(self.clock() // 3600)}"
        n = await self.redis.incr(key)
        await self.redis.expire(key, 7200)
        return n <= self.per_hour


def channel_turn_message(channel: str, recent: list[str], text: str) -> str:
    history = "\n".join(recent[-10:]) or "(none)"
    return (f"You are watching #{channel}. Nobody addressed you. Recent messages:\n{history}\n\nNew message:\n{text}\n\n"
            "Decide as your constitution describes whether to join. Search first if the record might matter. Start your "
            "reply with exactly one line: SILENT, or REACT :emoji_name:, or REPLY followed by your message on the next "
            "lines. A reply goes in the message's thread.")


async def consider(event, client, api, triage, budget, channel_name: str, recent: list[str], user_id) -> str:
    text = event["text"]
    if not await triage(TRIAGE_PROMPT.format(channel=channel_name, recent="\n".join(recent[-10:]) or "(none)", text=text)):
        return "skipped"
    if not await budget.take():
        return "over_budget"
    thread_ts = event.get("thread_ts") or event["ts"]
    answer = None
    async for name, data in api.ask(channel_turn_message(channel_name, recent, text),
                                    conversation_id(event["channel"], thread_ts), user_id, cache=False):
        if name == "answer":
            answer = data
        elif name == "error":
            log.warning("proactive turn failed: %s", data.get("message"))
            return "error"
    if answer is None:
        return "error"
    d = parse_decision(answer["text"])
    if d.kind == "react":
        await client.reactions_add(channel=event["channel"], timestamp=event["ts"], name=d.emoji)
        return "reacted"
    if d.kind == "reply" and d.text:
        await client.chat_postMessage(channel=event["channel"], thread_ts=thread_ts,
                                      text=to_mrkdwn(footnotes(d.text, answer["citations"])))
        return "replied"
    return "silent"
