"""Stands in for `codex exec --json`: records argv and stdin, prints a real-shaped event stream."""
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({"argv": sys.argv[2:], "stdin": sys.stdin.read()}))
for line in [
    {"type": "thread.started", "thread_id": "thread-123"},
    {"type": "turn.started"},
    {"type": "item.started", "item": {"id": "item_0", "type": "mcp_tool_call", "server": "orgbrain", "tool": "search",
                                       "arguments": {"query": "rollback"}, "result": None, "error": None, "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "item_0", "type": "mcp_tool_call", "server": "orgbrain", "tool": "search",
                                         "arguments": {"query": "rollback"},
                                         "result": {"content": [], "structured_content": {"results": [{"ref": "a1b2c3"}]}},
                                         "error": None, "status": "completed"}},
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "Pin the tag [a1b2c3]."}},
    {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 5}},
]:
    print(json.dumps(line), flush=True)
