import fakeredis
import pytest

from orgbrain.slack.proactive import Budget, channel_turn_message, consider, parse_triage


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_parse_triage():
    assert parse_triage("YES") and parse_triage("yes, it asks about the freeze")
    assert not parse_triage("NO") and not parse_triage("") and not parse_triage("maybe")


@pytest.mark.anyio
async def test_budget_caps_per_hour():
    b = Budget(fakeredis.aioredis.FakeRedis(), per_hour=2, clock=lambda: 3600 * 5 + 10)
    assert [await b.take() for _ in range(3)] == [True, True, False]


def test_channel_turn_message_frames_the_decision():
    m = channel_turn_message("eng-runtime", ["maya: p99 up 3x"], "is the freeze this week?")
    assert "#eng-runtime" in m and "maya: p99 up 3x" in m and "is the freeze this week?" in m
    assert "SILENT" in m and "REACT" in m and "REPLY" in m


class Client:
    def __init__(self):
        self.calls = []

    async def chat_postMessage(self, **kw):
        self.calls.append(("post", kw))
        return {"ts": "9.9"}

    async def reactions_add(self, **kw):
        self.calls.append(("react", kw))
        return {}


class Api:
    def __init__(self, text):
        self.text, self.asked = text, []

    async def ask(self, message, conversation_id, user_id=None, cache=True):
        self.asked.append(cache)
        yield "answer", {"text": self.text, "citations": []}


EVENT = {"channel": "C1", "ts": "5.0", "text": "is the freeze this week?", "user": "U1"}


@pytest.mark.anyio
@pytest.mark.parametrize("text,outcome,call", [("SILENT", "silent", None), ("REACT :eyes:", "reacted", "react"),
                                                ("REPLY\nIt starts Jan 12.", "replied", "post")])
async def test_consider_acts_on_the_decision(text, outcome, call):
    client, api = Client(), Api(text)
    budget = Budget(fakeredis.aioredis.FakeRedis(), per_hour=5)

    async def triage(_):
        return True

    assert await consider(EVENT, client, api, triage, budget, "eng-runtime", [], None) == outcome
    assert [k for k, _ in client.calls] == ([call] if call else []) and api.asked == [False]


@pytest.mark.anyio
async def test_triage_no_means_no_agent_turn():
    api = Api("REPLY\nx")

    async def triage(_):
        return False

    assert await consider(EVENT, Client(), api, triage, Budget(fakeredis.aioredis.FakeRedis(), 5), "eng-runtime", [], None) == "skipped"
    assert api.asked == []


class FailingApi(Api):
    async def ask(self, message, conversation_id, user_id=None, cache=True):
        self.asked.append(cache)
        yield "error", {"message": "codex turn failed: usage limit"}


@pytest.mark.anyio
async def test_failed_turn_is_an_error_not_silence():
    async def triage(_):
        return True

    client = Client()
    assert await consider(EVENT, client, FailingApi(""), triage, Budget(fakeredis.aioredis.FakeRedis(), 5), "eng-runtime", [], None) == "error"
    assert client.calls == []
