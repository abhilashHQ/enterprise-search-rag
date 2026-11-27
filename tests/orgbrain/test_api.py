import httpx
import pytest

from api_helpers import FakeRuntime, app_for, ask, parse_sse
from orgbrain.api import create_app
from orgbrain.runtime.events import Done, Message, ToolCall, ToolResult

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_ask_streams_steps_and_a_cited_answer():
    rt = FakeRuntime()
    status, events = await ask((await app_for(rt))[0], {"message": "rollback?"})
    assert status == 200
    assert [n for n, _ in events] == ["step", "step", "message", "answer", "done"]
    assert events[1][1] == {"kind": "tool_result", "tool": "search", "count": 1, "error": None}
    answer = events[3][1]
    assert answer["citations"] == [{"ref": "a1b2c3", "doc_id": "d1", "source": "confluence", "title": "Runbook"}]
    assert answer["conversation_id"]


@pytest.mark.anyio
async def test_follow_up_resumes_the_runtime_session():
    rt = FakeRuntime()
    app, _ = await app_for(rt)
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

    _, events = await ask((await app_for(Broken()))[0], {"message": "q"})
    assert events == [("error", {"message": "codex exited"})]


@pytest.mark.anyio
async def test_health_reports_runtime():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=(await app_for(FakeRuntime()))[0]), base_url="http://t") as c:
        assert (await c.get("/api/health")).json() == {"status": "ok", "runtime": "fake", "model": None}


@pytest.mark.anyio
async def test_turn_is_saved_with_citations():
    app, store = await app_for(FakeRuntime())
    _, events = await ask(app, {"message": "rollback?"})
    msgs = await store.messages(events[3][1]["conversation_id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["citations"][0]["ref"] == "a1b2c3"


class FakeMemories:
    async def list(self, status=None):
        return [{"id": 1, "status": status or "pending"}]

    async def decide(self, mid, action, user_id):
        if user_id != "maria":
            raise PermissionError("not admin")
        return {"id": mid, "status": "approved"}


@pytest.mark.anyio
async def test_memory_endpoints_enforce_admin():
    _, store = await app_for(FakeRuntime())
    app = create_app(FakeRuntime(), store, memories=FakeMemories())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/memories?status=pending")).json() == [{"id": 1, "status": "pending"}]
        assert (await c.post("/api/memories/1/approve", json={"user_id": "sam"})).status_code == 403
        assert (await c.post("/api/memories/1/approve", json={"user_id": "maria"})).json()["status"] == "approved"


class RecordingRuntime(FakeRuntime):
    def __init__(self):
        super().__init__()
        self.messages = []

    async def run(self, message, session_id=None):
        self.messages.append(message)
        async for ev in super().run(message, session_id):
            yield ev


async def cached_app(rt):
    import fakeredis

    from orgbrain.cache import SemanticCache

    _, store = await app_for(rt)
    cache = SemanticCache(fakeredis.aioredis.FakeRedis())
    return create_app(rt, store, cache=cache, embed=lambda text: [1.0, 0.0, 0.0]), store


@pytest.mark.anyio
async def test_repeat_question_comes_from_the_cache_and_rerun_bypasses_it():
    rt = RecordingRuntime()
    app, _ = await cached_app(rt)
    await ask(app, {"message": "rollback?"})
    _, events = await ask(app, {"message": "rollback?"})
    assert [n for n, _ in events] == ["answer", "done"] and events[0][1]["from_cache"] and events[1][1]["from_cache"]
    assert events[0][1]["text"] == "Pin the previous tag [a1b2c3]." and len(rt.sessions) == 1
    _, events = await ask(app, {"message": "rollback?", "rerun": True})
    assert "from_cache" not in events[-2][1] and len(rt.sessions) == 2


@pytest.mark.anyio
async def test_follow_up_to_a_cached_answer_carries_the_earlier_turn():
    rt = RecordingRuntime()
    app, _ = await cached_app(rt)
    await ask(app, {"message": "rollback?"})
    _, events = await ask(app, {"message": "rollback?"})
    await ask(app, {"message": "and staging?", "conversation_id": events[0][1]["conversation_id"]})
    assert rt.sessions == [None, None]
    cid = events[0][1]["conversation_id"]
    assert rt.messages[-1] == (f"(conversation {cid})\n\nEarlier in this conversation:\nuser: rollback?\n"
                               "assistant: Pin the previous tag [a1b2c3].\n\nand staging?")


class FakePeople:
    async def get(self, pid):
        return {"id": pid, "name": "Maria Lopez"} if pid == "maria" else None


@pytest.mark.anyio
async def test_the_runtime_message_carries_the_teammate_and_conversation_ids():
    rt = RecordingRuntime()
    _, store = await app_for(rt)
    app = create_app(rt, store, people=FakePeople())
    _, events = await ask(app, {"message": "remember X", "user_id": "maria"})
    cid = events[-2][1]["conversation_id"]
    assert rt.messages[-1] == f"(Teammate: Maria Lopez, id maria; conversation {cid})\n\nremember X"
    await ask(app, {"message": "q", "user_id": "nobody", "conversation_id": cid})
    assert rt.messages[-1] == f"(conversation {cid})\n\nq"


@pytest.mark.anyio
async def test_cache_false_neither_reads_nor_writes_the_cache():
    import fakeredis

    from orgbrain.cache import VECS, SemanticCache

    rt = RecordingRuntime()
    _, store = await app_for(rt)
    redis = fakeredis.aioredis.FakeRedis()
    app = create_app(rt, store, cache=SemanticCache(redis), embed=lambda text: [1.0, 0.0, 0.0])
    await ask(app, {"message": "rollback?", "cache": False})
    await ask(app, {"message": "rollback?", "cache": False})
    assert len(rt.sessions) == 2 and await redis.hlen(VECS) == 0


class ProposingRuntime(FakeRuntime):
    async def run(self, message, session_id=None):
        yield ToolCall("propose_memory", {"fact": "x"})
        yield ToolResult("propose_memory", {"fact": "x"}, {"id": 7, "status": "pending"}, None)
        yield Message("Proposed.")
        yield Done("s", {})


@pytest.mark.anyio
async def test_propose_memory_step_carries_the_memory_id():
    app, _ = await app_for(ProposingRuntime())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        events = parse_sse((await c.post("/api/ask", json={"message": "remember x"})).text)
    step = [d for n, d in events if n == "step" and d["kind"] == "tool_result"][0]
    assert step["memory_id"] == 7
