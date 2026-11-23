from dataclasses import dataclass


@dataclass
class ToolCall:
    tool: str
    arguments: dict


@dataclass
class ToolResult:
    tool: str
    arguments: dict
    result: dict | None
    error: str | None


@dataclass
class Message:
    text: str


@dataclass
class Session:
    session_id: str


@dataclass
class Done:
    session_id: str | None
    usage: dict


Event = ToolCall | ToolResult | Message | Session | Done
