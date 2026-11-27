"""Which runtime and model answer the next question, saved in Postgres and switchable without restarting the API.
Only the name of the env var holding an API key is stored; the key stays in the API process's environment."""

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace

from orgbrain.db import AppSetting

RUNTIMES = {"codex", "api"}
EFFORTS = {"minimal", "low", "medium", "high"}
KEY = "runtime"


@dataclass(frozen=True)
class RuntimeConfig:
    runtime: str = "codex"
    model: str = "gpt-6-luna"
    effort: str = "low"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"


def validate(cfg: RuntimeConfig) -> RuntimeConfig:
    cfg = replace(cfg, model=cfg.model.strip(), base_url=(cfg.base_url or "").strip() or None,
                  api_key_env=cfg.api_key_env.strip())
    if cfg.runtime not in RUNTIMES:
        raise ValueError(f"runtime must be one of {', '.join(sorted(RUNTIMES))}")
    if not cfg.model:
        raise ValueError("model is empty")
    if cfg.effort not in EFFORTS:
        raise ValueError("effort must be minimal, low, medium or high")
    if cfg.runtime == "api":
        if not (cfg.base_url or "").startswith("http"):
            raise ValueError("base url must start with http")
        if cfg.api_key_env not in os.environ:
            raise ValueError(f"{cfg.api_key_env} is not set on the server")
    return cfg


def build_runtime(cfg: RuntimeConfig, mcp_url: str, rules: str):
    from entsearch.data import ROOT

    if cfg.runtime == "codex":
        from orgbrain.runtime.codex import CodexConfig, CodexRuntime

        return CodexRuntime(CodexConfig(model=cfg.model, effort=cfg.effort, mcp_url=mcp_url,
                                        workdir=ROOT / "data/codex_work"), rules)
    from openai import AsyncOpenAI

    from orgbrain.runtime.api_loop import ApiRuntime, McpToolCaller

    client = AsyncOpenAI(base_url=cfg.base_url, api_key=os.environ[cfg.api_key_env])
    return ApiRuntime(client, cfg.model, McpToolCaller(mcp_url), rules)


class RuntimeSettings:
    def __init__(self, sessions, defaults: RuntimeConfig, build: Callable[[RuntimeConfig], object]):
        self.sessions, self.defaults, self.build = sessions, defaults, build
        self._built: dict[RuntimeConfig, object] = {}

    async def get(self) -> RuntimeConfig:
        async with self.sessions() as s:
            row = await s.get(AppSetting, KEY)
        names = {f.name for f in fields(RuntimeConfig)}
        return replace(self.defaults, **{k: v for k, v in (row.value if row else {}).items() if k in names})

    async def set(self, cfg: RuntimeConfig) -> RuntimeConfig:
        cfg = validate(cfg)
        async with self.sessions.begin() as s:
            await s.merge(AppSetting(key=KEY, value=asdict(cfg)))
        return cfg

    async def runtime(self):
        cfg = await self.get()
        if cfg not in self._built:
            self._built[cfg] = self.build(cfg)
        return self._built[cfg]
