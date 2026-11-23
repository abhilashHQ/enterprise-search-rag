"""Agent runtime for API keys: an OpenAI-compatible chat-completions tool loop over the orgbrain search server.

Works with any endpoint that speaks chat completions with tools (OpenAI, OpenRouter, Bedrock, Ollama, vLLM).
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from orgbrain.runtime.events import Done, Event, Message, ToolCall, ToolResult
from orgbrain.tools import TOOL_SPECS


class ToolCaller(Protocol):
    async def __call__(self, name: str, arguments: dict) -> dict: ...


class McpToolCaller:
    def __init__(self, url: str = "http://127.0.0.1:8765/mcp"):
        self.url = url

    async def __call__(self, name: str, arguments: dict) -> dict:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        from orgbrain.mcp_server import structured

        async with streamable_http_client(self.url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
        if getattr(result, "is_error", None) or getattr(result, "isError", None):
            raise RuntimeError(" ".join(getattr(c, "text", "") for c in result.content) or "tool error")
        return structured(result)


class ApiRuntime:
    name = "api"

    def __init__(self, client, model: str, tools: ToolCaller, instructions: str, max_steps: int = 8):
        self.client, self.model, self.tools = client, model, tools
        self.instructions, self.max_steps = instructions, max_steps
        self.sessions: dict[str, list[dict]] = {}

    async def run(self, message: str, session_id: str | None = None) -> AsyncIterator[Event]:
        sid = session_id or uuid.uuid4().hex
        msgs = self.sessions.get(sid) or [{"role": "system", "content": self.instructions}]
        msgs.append({"role": "user", "content": message})
        usage = {"input_tokens": 0, "output_tokens": 0}
        for _ in range(self.max_steps):
            resp = await self.client.chat.completions.create(model=self.model, messages=msgs, tools=TOOL_SPECS)
            usage["input_tokens"] += resp.usage.prompt_tokens
            usage["output_tokens"] += resp.usage.completion_tokens
            m = resp.choices[0].message
            msgs.append(m.model_dump(exclude_none=True))
            if not m.tool_calls:
                yield Message(m.content or "")
                break
            for tc in m.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                yield ToolCall(tc.function.name, args)
                try:
                    result, error = await self.tools(tc.function.name, args), None
                except Exception as e:
                    result, error = None, str(e)
                yield ToolResult(tc.function.name, args, result, error)
                msgs.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result if error is None else {"error": error})})
        else:
            yield Message("I hit my step limit before finishing. Try a narrower question.")
        self.sessions[sid] = msgs
        yield Done(sid, usage)
