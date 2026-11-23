import json
from types import SimpleNamespace

import anyio

from orgbrain.runtime.api_loop import ApiRuntime
from orgbrain.runtime.events import Done, Message, ToolCall, ToolResult


class Msg(SimpleNamespace):
    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [{"id": t.id, "type": "function",
                                "function": {"name": t.function.name, "arguments": t.function.arguments}} for t in self.tool_calls]
        return d


def reply(content=None, tool=None, args=None):
    calls = [SimpleNamespace(id="call_1", function=SimpleNamespace(name=tool, arguments=json.dumps(args)))] if tool else None
    return SimpleNamespace(choices=[SimpleNamespace(message=Msg(content=content, tool_calls=calls))],
                           usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))


class FakeClient:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, model, messages, tools):
        self.sent.append([dict(m) for m in messages])
        return self.replies.pop(0)


def collect(rt, message, session=None):
    async def go():
        return [e async for e in rt.run(message, session)]
    return anyio.run(go)


def test_tool_loop_then_answer():
    calls = []

    async def tools(name, arguments):
        calls.append((name, arguments))
        return {"results": [{"ref": "a1b2c3"}]}

    client = FakeClient([reply(tool="search", args={"query": "rollback"}), reply(content="Pin it [a1b2c3].")])
    events = collect(ApiRuntime(client, "m", tools, "RULES"), "how?")
    assert [type(e) for e in events] == [ToolCall, ToolResult, Message, Done]
    assert calls == [("search", {"query": "rollback"})]
    assert events[2] == Message("Pin it [a1b2c3].") and events[3].usage == {"input_tokens": 20, "output_tokens": 4}
    assert client.sent[0][0] == {"role": "system", "content": "RULES"}
    assert client.sent[1][-1]["role"] == "tool" and "a1b2c3" in client.sent[1][-1]["content"]


def test_tool_error_is_reported_to_model_and_caller():
    async def tools(name, arguments):
        raise RuntimeError("index not loaded")

    client = FakeClient([reply(tool="search", args={"query": "x"}), reply(content="Sorry.")])
    events = collect(ApiRuntime(client, "m", tools, "RULES"), "q")
    assert events[1] == ToolResult("search", {"query": "x"}, None, "index not loaded")
    assert "index not loaded" in client.sent[1][-1]["content"]


def test_session_keeps_history():
    async def tools(name, arguments):
        return {}

    client = FakeClient([reply(content="first"), reply(content="second")])
    rt = ApiRuntime(client, "m", tools, "RULES")
    sid = collect(rt, "one")[-1].session_id
    collect(rt, "two", sid)
    assert [m["content"] for m in client.sent[1] if m["role"] == "user"] == ["one", "two"]


def test_step_limit_ends_the_turn():
    async def tools(name, arguments):
        return {}

    client = FakeClient([reply(tool="search", args={"query": "x"})] * 3)
    events = collect(ApiRuntime(client, "m", tools, "RULES", max_steps=2), "q")
    assert isinstance(events[-1], Done) and "step limit" in events[-2].text
