import httpx
import pytest

from api_helpers import FakeRuntime, app_for, ask
from orgbrain.api import create_app
from orgbrain.docs import DocReader
from orgbrain.people import PeopleStore
from orgbrain.runtime.events import Done, Message
from test_docs import make_docs

PEOPLE = [{"id": "monica.patel", "name": "Monica Patel", "role": "VP Engineering", "team": "Platform",
           "topics": ["billing"], "doc_count": 40},
          {"id": "maria.garcia", "name": "Maria Garcia", "role": "SRE", "team": "Infra", "topics": ["canary"],
           "doc_count": 90}]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.mark.anyio
async def test_conversations_are_listed_for_their_owner_and_readable():
    app, _ = await app_for(FakeRuntime())
    _, events = await ask(app, {"message": "rollback?", "user_id": "maria"})
    cid = events[-2][1]["conversation_id"]
    async with client(app) as c:
        rows = (await c.get("/api/conversations", params={"user_id": "maria"})).json()
        assert [(r["id"], r["title"]) for r in rows] == [(cid, "rollback?")]
        assert (await c.get("/api/conversations", params={"user_id": "vivek"})).json() == []
        conv = (await c.get(f"/api/conversations/{cid}")).json()
        assert conv["user_id"] == "maria" and [m["role"] for m in conv["messages"]] == ["user", "assistant"]
        r = await c.get("/api/conversations/nope")
        assert r.status_code == 404 and "error" in r.json()


async def web_app(tmp_path, **kw):
    _, store = await app_for(FakeRuntime())
    people = PeopleStore(store.sessions)
    await people.replace_all(PEOPLE)
    live = make_docs(tmp_path / "live.sqlite", [("file:notes:sub/a.md", "files", "a", "notes body")])
    docs = DocReader(make_docs(tmp_path / "docstore.sqlite", [("d1", "confluence", "Runbook", "x")]), live)
    return create_app(FakeRuntime(), store, people=people, docs=docs, **kw), store


@pytest.mark.anyio
async def test_documents_by_id_and_people_search(tmp_path):
    app, _ = await web_app(tmp_path)
    async with client(app) as c:
        d = (await c.get("/api/documents/file:notes:sub/a.md")).json()
        assert d == {"doc_id": "file:notes:sub/a.md", "source": "files", "title": "a", "content": "notes body"}
        assert (await c.get("/api/documents/d1")).json()["title"] == "Runbook"
        r = await c.get("/api/documents/nope")
        assert r.status_code == 404 and "error" in r.json()
        assert [p["name"] for p in (await c.get("/api/people", params={"q": "billing"})).json()] == ["Monica Patel"]
        assert [p["id"] for p in (await c.get("/api/people")).json()] == ["maria.garcia", "monica.patel"]
        assert (await c.get("/api/people/monica.patel")).json()["role"] == "VP Engineering"
        assert (await c.get("/api/people/nobody")).status_code == 404


@pytest.mark.anyio
async def test_propose_from_the_memory_page():
    from orgbrain.memory import MemoryStore

    _, store = await app_for(FakeRuntime())
    mem = MemoryStore(store.sessions)
    app = create_app(FakeRuntime(), store, memories=mem)
    async with client(app) as c:
        assert (await c.post("/api/memories", json={"text": "   ", "user_id": "maria"})).status_code == 422
        r = await c.post("/api/memories", json={"text": " billing moved to payments ", "user_id": "maria"})
        mid = r.json()["id"]
        rows = (await c.get("/api/memories", params={"status": "pending"})).json()
    assert [(m["id"], m["text"], m["status"], m["proposed_by"]) for m in rows] == [
        (mid, "billing moved to payments", "pending", "maria")]


@pytest.mark.anyio
async def test_uploads_sync_into_the_outbox_and_show_in_sources(tmp_path):
    from sqlalchemy import select

    from orgbrain.db import ConnectorSource, Outbox

    app, store = await web_app(tmp_path, uploads=tmp_path / "uploads")
    files = [("files", ("a.md", b"# a\nalpha", "text/markdown")), ("files", ("b.md", b"beta", "text/markdown"))]
    async with client(app) as c:
        r = (await c.post("/api/sources/uploads", files=files)).json()
        assert r == {"saved": ["a.md", "b.md"], "added": 2, "updated": 0, "deleted": 0, "skipped": []}
        bad = await c.post("/api/sources/uploads", files=[("files", (".env", b"k", "text/plain"))])
        assert bad.status_code == 422
        overview = (await c.get("/api/sources")).json()
        assert overview["corpus"] == {"confluence": 1, "files": 1} and overview["pending"] == 2
        [up] = overview["connectors"]
        assert (up["id"], up["kind"], up["files"], up["indexed"]) == ("uploads", "folder", 2, 0)
        assert up["last_synced_at"]
        again = (await c.post("/api/sources/uploads/sync")).json()
        assert (again["added"], again["updated"]) == (0, 0)
        assert (await c.post("/api/sources/nope/sync")).status_code == 404
        async with store.sessions.begin() as s:
            s.add(ConnectorSource(id="gone", kind="folder", config={"path": str(tmp_path / "gone")}))
        assert (await c.post("/api/sources/gone/sync")).status_code == 409
    async with store.sessions() as s:
        rows = [(o.kind, o.doc_id) for o in (await s.execute(select(Outbox).order_by(Outbox.id))).scalars()]
    assert rows == [("upsert", "file:uploads:a.md"), ("upsert", "file:uploads:b.md")]


class NamedRuntime(FakeRuntime):
    def __init__(self, cfg):
        super().__init__()
        self.name, self.cfg = cfg.runtime, cfg

    async def run(self, message, session_id=None):
        yield Message(f"answered by {self.cfg.model}")
        yield Done(f"{self.cfg.model}-session", {})


@pytest.mark.anyio
async def test_settings_switch_the_runtime_for_the_next_question(monkeypatch):
    from orgbrain.runtime_settings import RuntimeConfig, RuntimeSettings

    monkeypatch.delenv("ORGBRAIN_TEST_KEY", raising=False)
    _, store = await app_for(FakeRuntime())
    runtimes = RuntimeSettings(store.sessions, RuntimeConfig(), NamedRuntime)
    app = create_app(None, store, runtimes=runtimes)
    async with client(app) as c:
        got = (await c.get("/api/settings")).json()
        assert got["runtime"]["model"] == "gpt-6-luna" and got["runtime"]["runtime"] == "codex"
        assert (await c.get("/api/health")).json() == {"status": "ok", "runtime": "codex", "model": "gpt-6-luna"}
        bad = await c.put("/api/settings", json={**got["runtime"], "runtime": "api", "base_url": "https://x/v1",
                                                 "api_key_env": "ORGBRAIN_TEST_KEY"})
        assert bad.status_code == 422 and "not set" in bad.json()["error"]
    _, events = await ask(app, {"message": "q"})
    assert events[-2][1]["text"] == "answered by gpt-6-luna"
    cid = events[-2][1]["conversation_id"]
    async with client(app) as c:
        ok = await c.put("/api/settings", json={**got["runtime"], "model": "gpt-6.2-sol", "effort": "medium"})
        assert ok.json()["model"] == "gpt-6.2-sol"
        assert (await c.get("/api/health")).json()["model"] == "gpt-6.2-sol"
    _, events = await ask(app, {"message": "q2", "conversation_id": cid})
    assert events[-2][1]["text"] == "answered by gpt-6.2-sol"


@pytest.mark.anyio
async def test_the_event_stream_tells_proxies_not_to_compress_it():
    app, _ = await app_for(FakeRuntime())
    async with client(app) as c:
        r = await c.post("/api/ask", json={"message": "q"})
    assert "no-transform" in r.headers["cache-control"]
