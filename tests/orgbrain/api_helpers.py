import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.api import create_app
from orgbrain.db import Base, ConversationStore
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


async def app_for(runtime):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = ConversationStore(engine)
    return create_app(runtime, store), store


async def ask(app, body):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/ask", json=body)
        return r.status_code, parse_sse(r.text)
