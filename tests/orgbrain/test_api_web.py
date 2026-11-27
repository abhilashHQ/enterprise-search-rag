import httpx
import pytest

from api_helpers import FakeRuntime, app_for, ask


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

