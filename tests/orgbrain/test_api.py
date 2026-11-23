import json

import httpx
import pytest

from orgbrain.api import create_app
from orgbrain.runtime.events import Done, Message, ToolCall, ToolResult

HIT = {"ref": "a1b2c3", "doc_id": "d1", "source": "confluence", "title": "Runbook", "snippet": "", "score": 1.0}


class FakeRuntime:
    name = "fake"

    def __init__(self):
        self.sessions = []

    async def run(self, message, session_id=None):
        self.sessions.append(session_id)
        yield ToolCall("search", {"query": message})
        yield ToolResult("search", {"query": message}, {"results": [HIT]}, None)
        yield Message("Pin the previous tag [a1b2c3].")
        yield Done("sess-1", {"input_tokens": 5})


def parse_sse(text):
    events, name = [], None
    for line in text.splitlines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            events.append((name, json.loads(line.split(":", 1)[1].strip())))
    return events


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def ask(app, body):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/ask", json=body)
        return r.status_code, parse_sse(r.text)


@pytest.mark.anyio
async def test_ask_streams_steps_and_a_cited_answer():
    rt = FakeRuntime()
    status, events = await ask(create_app(rt), {"message": "rollback?"})
    assert status == 200
    assert [n for n, _ in events] == ["step", "step", "message", "answer", "done"]
    assert events[1][1] == {"kind": "tool_result", "tool": "search", "count": 1, "error": None}
    answer = events[3][1]
    assert answer["citations"] == [{"ref": "a1b2c3", "doc_id": "d1", "source": "confluence", "title": "Runbook"}]
    assert answer["conversation_id"]


@pytest.mark.anyio
async def test_follow_up_resumes_the_runtime_session():
    rt = FakeRuntime()
    app = create_app(rt)
    _, events = await ask(app, {"message": "one"})
    cid = events[3][1]["conversation_id"]
    await ask(app, {"message": "two", "conversation_id": cid})
    assert rt.sessions == [None, "sess-1"]


@pytest.mark.anyio
async def test_runtime_failure_becomes_an_error_event():
    class Broken(FakeRuntime):
        async def run(self, message, session_id=None):
            raise RuntimeError("codex exited")
            yield

    _, events = await ask(create_app(Broken()), {"message": "q"})
    assert events == [("error", {"message": "codex exited"})]


@pytest.mark.anyio
async def test_health_reports_runtime():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(FakeRuntime())), base_url="http://t") as c:
        assert (await c.get("/api/health")).json() == {"status": "ok", "runtime": "fake"}
