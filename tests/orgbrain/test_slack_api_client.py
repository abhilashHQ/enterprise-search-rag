import json

import httpx
import pytest

from orgbrain.slack.api_client import OrgbrainApi, iter_sse


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_iter_sse_pairs_events_with_data():
    lines = ["event: step", 'data: {"kind": "tool_call"}', "", "event: answer", 'data: {"text": "hi"}', ""]
    assert list(iter_sse(lines)) == [("step", {"kind": "tool_call"}), ("answer", {"text": "hi"})]


@pytest.mark.anyio
async def test_ask_waits_out_a_busy_api_then_streams():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(409, json={"error": "busy"})
        return httpx.Response(200, text='event: answer\ndata: {"text": "ok"}\n\n', headers={"content-type": "text/event-stream"})

    api = OrgbrainApi("http://t", httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t"), retry_every=0)
    events = [e async for e in api.ask("q", "c1", user_id="monica.patel", cache=False)]
    assert events == [("answer", {"text": "ok"})] and len(calls) == 2
    assert calls[1] == {"message": "q", "conversation_id": "c1", "user_id": "monica.patel", "cache": False}
