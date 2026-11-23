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
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine
from sse_starlette.sse import EventSourceResponse

from entsearch.data import ROOT
from orgbrain.answer import collect_hits, finalize
from orgbrain.config import Settings
from orgbrain.db import ConversationStore
from orgbrain.instructions import instructions
from orgbrain.runtime.events import Done, Message, ToolCall, ToolResult


class AskRequest(BaseModel):
    message: str
    conversation_id: str | None = None


def create_app(runtime, store: ConversationStore) -> FastAPI:
    app = FastAPI(title="orgbrain")
    busy = asyncio.Lock()

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "runtime": runtime.name}

    @app.post("/api/ask")
    async def ask(req: AskRequest):
        if busy.locked():
            return JSONResponse({"error": "busy: one question at a time"}, status_code=409)
        cid = req.conversation_id or uuid.uuid4().hex

        async def stream():
            async with busy:
                start, results, text = time.perf_counter(), [], ""
                try:
                    prior = await store.runtime_session(cid)
                    async for ev in runtime.run(req.message, prior):
                        if isinstance(ev, ToolCall):
                            yield {"event": "step", "data": json.dumps({"kind": "tool_call", "tool": ev.tool, "arguments": ev.arguments})}
                        elif isinstance(ev, ToolResult):
                            if ev.result:
                                results.append(ev.result)
                            count = len(ev.result["results"]) if ev.result and "results" in ev.result else None
                            yield {"event": "step", "data": json.dumps({"kind": "tool_result", "tool": ev.tool, "count": count, "error": ev.error})}
                        elif isinstance(ev, Message):
                            text = ev.text
                            yield {"event": "message", "data": json.dumps({"text": ev.text})}
                        elif isinstance(ev, Done):
                            answer = asdict(finalize(text, collect_hits(results)))
                            await store.save_turn(cid, runtime.name, ev.session_id, req.message, answer["text"],
                                                  answer["citations"])
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
    store = ConversationStore(create_async_engine(Settings.from_env().database_url))
    uvicorn.run(create_app(runtime, store), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
