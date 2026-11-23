"""Codex CLI as the agent runtime: one `codex exec --json` per user turn, tools from the orgbrain search server by URL.

The CLI runs the agent loop on the user's ChatGPT plan. The conversation continues with `codex exec resume <thread>`.
"""

import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from orgbrain.runtime.events import Done, Event, Message, Session, ToolCall, ToolResult


@dataclass
class CodexConfig:
    command: list[str] = field(default_factory=lambda: ["codex"])
    model: str = "gpt-6-luna"
    effort: str = "low"
    mcp_url: str = "http://127.0.0.1:8765/mcp"
    workdir: Path | None = None


def build_argv(cfg: CodexConfig, session_id: str | None) -> list[str]:
    exe = shutil.which(cfg.command[0]) or cfg.command[0]
    argv = [exe, *cfg.command[1:], "exec", "--json", "--skip-git-repo-check", "-s", "read-only", "-m", cfg.model,
            "-c", f'model_reasoning_effort="{cfg.effort}"',
            "-c", f'mcp_servers.orgbrain.url="{cfg.mcp_url}"',
            "-c", 'mcp_servers.orgbrain.default_tools_approval_mode="approve"']
    return argv + (["resume", session_id] if session_id else []) + ["-"]


def parse_line(line: str) -> list[Event]:
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return []
    kind, item = ev.get("type"), ev.get("item") or {}
    if kind == "thread.started":
        return [Session(ev["thread_id"])]
    if kind == "item.started" and item.get("type") == "mcp_tool_call":
        return [ToolCall(item["tool"], item.get("arguments") or {})]
    if kind == "item.completed" and item.get("type") == "mcp_tool_call":
        result, error = item.get("result") or {}, item.get("error")
        return [ToolResult(item["tool"], item.get("arguments") or {}, result.get("structured_content"),
                           error.get("message") if error else None)]
    if kind == "item.completed" and item.get("type") == "agent_message":
        return [Message(item.get("text", ""))]
    if kind == "turn.completed":
        return [Done(None, ev.get("usage") or {})]
    if kind in ("turn.failed", "error"):
        err = ev.get("error") or {}
        raise RuntimeError(f"codex turn failed: {err.get('message') if isinstance(err, dict) else err or ev}")
    return []


class CodexRuntime:
    name = "codex"

    def __init__(self, cfg: CodexConfig, instructions: str):
        self.cfg, self.instructions = cfg, instructions

    async def run(self, message: str, session_id: str | None = None) -> AsyncIterator[Event]:
        prompt = message if session_id else f"{self.instructions}\n\n## Message from your teammate\n{message}"
        cwd = self.cfg.workdir
        if cwd is not None:
            cwd.mkdir(parents=True, exist_ok=True)
        # Raised stream limit: a tool result line can carry 20 snippets or a 12K-char document.
        proc = await asyncio.create_subprocess_exec(
            *build_argv(self.cfg, session_id), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=cwd, limit=16 * 1024 * 1024,
        )
        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()
        sid, finished = session_id, False
        async for raw in proc.stdout:
            for ev in parse_line(raw.decode(errors="replace")):
                if isinstance(ev, Session):
                    sid = ev.session_id
                elif isinstance(ev, Done):
                    finished = True
                    yield Done(sid, ev.usage)
                else:
                    yield ev
        err = (await proc.stderr.read()).decode(errors="replace")
        await proc.wait()
        if not finished:
            raise RuntimeError(f"codex exited with code {proc.returncode} before finishing the turn: {err[-1000:]}")
