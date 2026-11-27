import httpx
import pytest

from api_helpers import FakeRuntime, app_for, ask
from orgbrain.api import create_app
from orgbrain.docs import DocReader
from orgbrain.people import PeopleStore
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
