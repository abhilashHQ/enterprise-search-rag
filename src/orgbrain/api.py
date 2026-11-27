"""orgbrain API: one agent turn per request, every step streamed as a server-sent event.

  uv run --extra app alembic upgrade head               # once, with docker compose up
  uv run --extra app orgbrain-search                     # first, in its own terminal
  uv run --extra app orgbrain-api                        # Codex on your ChatGPT plan, model gpt-6-luna
  uv run --extra app orgbrain-api --runtime api --base-url https://openrouter.ai/api/v1 --model openai/gpt-5-mini
"""

import argparse
import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine
from sse_starlette.sse import EventSourceResponse

from entsearch.data import ROOT
from orgbrain.answer import collect_hits, collect_people, finalize
from orgbrain.config import Settings
from orgbrain.db import ConversationStore
from orgbrain.docs import DocReader
from orgbrain.instructions import instructions
from orgbrain.memory import MemoryStore
from orgbrain.people import PeopleStore
from orgbrain.runtime.events import Done, Message, ToolCall, ToolResult


class AskRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    user_id: str | None = None
    rerun: bool = False
    cache: bool = True


class DecideRequest(BaseModel):
    user_id: str


def create_app(runtime, store: ConversationStore, memories=None, people=None, cache=None, embed=None,
               docs: DocReader | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app):
        if docs is not None:
            await asyncio.to_thread(docs.counts)
        yield

    app = FastAPI(title="orgbrain", lifespan=lifespan)
    busy = asyncio.Lock()

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "runtime": runtime.name}

    @app.get("/api/documents/{doc_id:path}")
    async def document(doc_id: str):
        d = await asyncio.to_thread(docs.get, doc_id)
        return d if d else JSONResponse({"error": f"no document {doc_id}"}, status_code=404)

    @app.get("/api/people")
    async def find_people(q: str = "", k: int = 20):
        return await people.find(q, min(k, 100))

    @app.get("/api/people/{pid}")
    async def person(pid: str):
        p = await people.get(pid)
        return p if p else JSONResponse({"error": f"no person {pid}"}, status_code=404)

    @app.get("/api/memories")
    async def list_memories(status: str | None = None):
        return await memories.list(status)

    @app.post("/api/memories/{memory_id}/{action}")
    async def decide(memory_id: int, action: str, req: DecideRequest):
        try:
            return await memories.decide(memory_id, action, req.user_id)
        except PermissionError as e:
            return JSONResponse({"error": str(e)}, status_code=403)
        except LookupError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=409)

    @app.get("/api/conversations")
    async def conversations(user_id: str):
        return await store.list_for(user_id)

    @app.get("/api/conversations/{cid}")
    async def conversation(cid: str):
        c = await store.get(cid)
        return c if c else JSONResponse({"error": f"no conversation {cid}"}, status_code=404)

    @app.post("/api/ask")
    async def ask(req: AskRequest):
        if busy.locked():
            return JSONResponse({"error": "busy: one question at a time"}, status_code=409)
        cid = req.conversation_id or uuid.uuid4().hex

        async def stream():
            async with busy:
                start, results, text = time.perf_counter(), [], ""
                try:
                    use_cache = cache is not None and embed is not None and req.conversation_id is None and req.cache
                    qvec = await asyncio.to_thread(embed, req.message) if use_cache else None
                    if qvec is not None and not req.rerun and (hit := await cache.get(qvec)):
                        answer = {k: hit[k] for k in ("text", "citations")}
                        await store.save_turn(cid, runtime.name, None, req.message, answer["text"], answer["citations"],
                                              user_id=req.user_id)
                        yield {"event": "answer", "data": json.dumps({**answer, "conversation_id": cid, "from_cache": True})}
                        yield {"event": "done", "data": json.dumps({"seconds": round(time.perf_counter() - start, 2), "from_cache": True})}
                        return
                    prior = await store.runtime_session(cid)
                    message = req.message
                    if prior is None and req.conversation_id and (msgs := await store.messages(cid)):
                        earlier = "\n".join(f"{m['role']}: {m['text']}" for m in msgs)
                        message = f"Earlier in this conversation:\n{earlier}\n\n{message}"
                    person = await people.get(req.user_id) if req.user_id and people is not None else None
                    who = f"Teammate: {person['name']}, id {req.user_id}; " if person else ""
                    message = f"({who}conversation {cid})\n\n{message}"
                    async for ev in runtime.run(message, prior):
                        if isinstance(ev, ToolCall):
                            yield {"event": "step", "data": json.dumps({"kind": "tool_call", "tool": ev.tool, "arguments": ev.arguments})}
                        elif isinstance(ev, ToolResult):
                            if ev.result:
                                results.append(ev.result)
                            count = len(ev.result["results"]) if ev.result and "results" in ev.result else None
                            step = {"kind": "tool_result", "tool": ev.tool, "count": count, "error": ev.error}
                            if ev.tool == "propose_memory" and ev.result and "id" in ev.result:
                                step["memory_id"] = ev.result["id"]
                            yield {"event": "step", "data": json.dumps(step)}
                        elif isinstance(ev, Message):
                            text = ev.text
                            yield {"event": "message", "data": json.dumps({"text": ev.text})}
                        elif isinstance(ev, Done):
                            answer = asdict(finalize(text, collect_hits(results), collect_people(results)))
                            await store.save_turn(cid, runtime.name, ev.session_id, req.message, answer["text"],
                                                  answer["citations"], user_id=req.user_id)
                            if qvec is not None:
                                await cache.put(req.message, qvec, answer)
                            yield {"event": "answer", "data": json.dumps({**answer, "conversation_id": cid})}
                            yield {"event": "done", "data": json.dumps({"seconds": round(time.perf_counter() - start, 2), "usage": ev.usage})}
                except Exception as e:
                    yield {"event": "error", "data": json.dumps({"message": str(e)})}

        return EventSourceResponse(stream())

    return app


def main() -> None:
    import uvicorn

    from orgbrain.runtime.api_loop import ApiRuntime, McpToolCaller
    from orgbrain.runtime.codex import CodexConfig, CodexRuntime

    p = argparse.ArgumentParser(prog="orgbrain-api", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runtime", choices=["codex", "api"], default="codex")
    p.add_argument("--model", default="gpt-6-luna")
    p.add_argument("--effort", default="low", help="reasoning effort (codex runtime)")
    p.add_argument("--mcp-url", default="http://127.0.0.1:8765/mcp")
    p.add_argument("--base-url", help="OpenAI-compatible endpoint (api runtime)")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY")
    p.add_argument("--company", default="Redwood Inference")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    rules = instructions(a.company)
    if a.runtime == "codex":
        runtime = CodexRuntime(CodexConfig(model=a.model, effort=a.effort, mcp_url=a.mcp_url,
                                           workdir=ROOT / "data/codex_work"), rules)
    else:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=a.base_url, api_key=os.environ[a.api_key_env])
        runtime = ApiRuntime(client, a.model, McpToolCaller(a.mcp_url), rules)
    from redis.asyncio import Redis

    from orgbrain.cache import SemanticCache
    from orgbrain.models_client import ModelsClient

    settings = Settings.from_env()
    store = ConversationStore(create_async_engine(settings.database_url))
    uvicorn.run(create_app(runtime, store, memories=MemoryStore(store.sessions), people=PeopleStore(store.sessions),
                           cache=SemanticCache(Redis.from_url(settings.redis_url)),
                           embed=ModelsClient(settings.models_url).embed_query,
                           docs=DocReader(settings.docstore_path, settings.live_path)), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
