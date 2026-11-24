import json
import sys
from pathlib import Path

import anyio
import pytest

from orgbrain.runtime.codex import CodexConfig, CodexRuntime, build_argv, parse_line
from orgbrain.runtime.events import Done, Message, Session, ToolCall, ToolResult

FAKE = Path(__file__).with_name("fake_codex.py")


def test_build_argv_first_turn_and_resume():
    cfg = CodexConfig(command=["codex-not-on-path"], model="gpt-6-luna", effort="low", mcp_url="http://h:1/mcp")
    first = build_argv(cfg, None)
    assert first[:2] == ["codex-not-on-path", "exec"] and first[-1] == "-" and "resume" not in first
    assert 'mcp_servers.orgbrain.url="http://h:1/mcp"' in first
    assert 'mcp_servers.orgbrain.default_tools_approval_mode="approve"' in first
    assert first[first.index("-s") + 1] == "read-only" and first[first.index("-m") + 1] == "gpt-6-luna"
    resumed = build_argv(cfg, "thread-9")
    assert resumed[-3:] == ["resume", "thread-9", "-"]


def test_parse_line_maps_codex_events():
    assert parse_line('{"type":"thread.started","thread_id":"t1"}') == [Session("t1")]
    started = parse_line(json.dumps({"type": "item.started", "item": {"type": "mcp_tool_call", "tool": "search", "arguments": {"query": "q"}}}))
    assert started == [ToolCall("search", {"query": "q"})]
    failed = parse_line(json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "search", "arguments": {},
                                                                         "result": None, "error": {"message": "boom"}}}))
    assert failed == [ToolResult("search", {}, None, "boom")]
    assert parse_line('{"type":"item.completed","item":{"type":"agent_message","text":"hi"}}') == [Message("hi")]
    assert parse_line('{"type":"turn.completed","usage":{"input_tokens":1}}') == [Done(None, {"input_tokens": 1})]
    assert parse_line('{"type":"turn.started"}') == [] and parse_line("not json") == []


def test_parse_line_raises_on_failed_turn():
    with pytest.raises(RuntimeError, match="quota"):
        parse_line('{"type":"turn.failed","error":{"message":"quota exceeded"}}')
    with pytest.raises(RuntimeError, match="usage limit"):
        parse_line('{"type":"error","message":"You have hit your usage limit."}')


def run_fake(tmp_path, message, session_id):
    record = tmp_path / "record.json"
    cfg = CodexConfig(command=[sys.executable, str(FAKE), str(record)], workdir=tmp_path)
    rt = CodexRuntime(cfg, instructions="RULES")

    async def collect():
        return [e async for e in rt.run(message, session_id)]

    return anyio.run(collect), json.loads(record.read_text())


def test_run_streams_events_and_returns_session(tmp_path):
    events, rec = run_fake(tmp_path, "how do I roll back?", None)
    assert [type(e) for e in events] == [ToolCall, ToolResult, Message, Done]
    assert events[1].result == {"results": [{"ref": "a1b2c3"}]}
    assert events[-1] == Done("thread-123", {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 5})
    assert rec["stdin"].startswith("RULES") and "how do I roll back?" in rec["stdin"]


def test_resume_sends_only_the_message(tmp_path):
    _, rec = run_fake(tmp_path, "and in staging?", "thread-123")
    assert rec["stdin"] == "and in staging?" and rec["argv"][-3:] == ["resume", "thread-123", "-"]
