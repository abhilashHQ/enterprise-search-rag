import pytest

from orgbrain.slack.bot import answer_in_thread, memory_blocks, strip_mention


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeClient:
    def __init__(self):
        self.calls = []

    async def chat_postMessage(self, **kw):
        self.calls.append(("post", kw))
        return {"ts": f"9.{len(self.calls)}"}

    async def chat_update(self, **kw):
        self.calls.append(("update", kw))
        return {}

    async def reactions_add(self, **kw):
        self.calls.append(("react", kw))
        return {}


class FakeApi:
    def __init__(self, events):
        self.events, self.asked = events, []

    async def ask(self, message, conversation_id, user_id=None, cache=True):
        self.asked.append((message, conversation_id, user_id, cache))
        for e in self.events:
            yield e


def test_strip_mention():
    assert strip_mention("<@U0BOT> when is the freeze?") == "when is the freeze?"


@pytest.mark.anyio
async def test_answer_streams_status_then_footnoted_answer_and_buttons():
    events = [("step", {"kind": "tool_call", "tool": "search", "arguments": {"query": "freeze"}}),
              ("step", {"kind": "tool_call", "tool": "propose_memory", "arguments": {"fact": "Freeze is Jan 12"}}),
              ("step", {"kind": "tool_result", "tool": "propose_memory", "count": None, "error": None, "memory_id": 7}),
              ("answer", {"text": "Jan 12 [a1b2c3].", "citations": [{"ref": "a1b2c3", "doc_id": "d", "source": "confluence", "title": "Freeze"}]}),
              ("done", {"seconds": 3.2})]
    client, api = FakeClient(), FakeApi(events)
    out = await answer_in_thread(client, api, "C1", "1.0", "when is the freeze?", "monica.patel", min_interval=0)
    assert out["text"] == "Jan 12 [a1b2c3]."
    kinds = [k for k, _ in client.calls]
    assert kinds[0] == "post" and client.calls[0][1]["thread_ts"] == "1.0"
    final = [kw for k, kw in client.calls if k == "update"][-1]
    assert final["text"] == "Jan 12 [1].\n\n[1] Freeze (confluence)"
    buttons = [kw for k, kw in client.calls[1:] if k == "post"][-1]
    assert buttons["blocks"] == memory_blocks(7, "Freeze is Jan 12")
    assert api.asked[0][2] == "monica.patel" and len(api.asked[0][1]) == 32


@pytest.mark.anyio
async def test_error_event_is_shown_not_swallowed():
    client = FakeClient()
    await answer_in_thread(client, FakeApi([("error", {"message": "codex turn failed: usage limit"})]), "C1", "1.0", "q", None, min_interval=0)
    assert "usage limit" in [kw for k, kw in client.calls if k == "update"][-1]["text"]


class DownApi:
    async def ask(self, message, conversation_id, user_id=None, cache=True):
        raise ConnectionError("api unreachable")
        yield


@pytest.mark.anyio
async def test_unreachable_api_replaces_the_status_with_the_error():
    client = FakeClient()
    assert await answer_in_thread(client, DownApi(), "C1", "1.0", "q", None, min_interval=0) is None
    assert "api unreachable" in [kw for k, kw in client.calls if k == "update"][-1]["text"]
