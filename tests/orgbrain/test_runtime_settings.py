import pytest

from api_helpers import app_for
from orgbrain.runtime_settings import RuntimeConfig, RuntimeSettings


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def settings(build=lambda cfg: cfg.model):
    _, store = await app_for(None)
    return RuntimeSettings(store.sessions, RuntimeConfig(), build)


@pytest.mark.anyio
async def test_defaults_then_round_trip():
    rs = await settings()
    assert await rs.get() == RuntimeConfig()
    saved = await rs.set(RuntimeConfig(model=" gpt-6.2-sol ", effort="medium"))
    assert saved == RuntimeConfig(model="gpt-6.2-sol", effort="medium") == await rs.get()


@pytest.mark.anyio
async def test_validation(monkeypatch):
    rs = await settings()
    with pytest.raises(ValueError, match="effort"):
        await rs.set(RuntimeConfig(effort="max"))
    with pytest.raises(ValueError, match="runtime"):
        await rs.set(RuntimeConfig(runtime="claude"))
    with pytest.raises(ValueError, match="base url"):
        await rs.set(RuntimeConfig(runtime="api", base_url="openrouter.ai"))
    monkeypatch.delenv("ORGBRAIN_TEST_KEY", raising=False)
    with pytest.raises(ValueError, match="ORGBRAIN_TEST_KEY is not set"):
        await rs.set(RuntimeConfig(runtime="api", base_url="https://x/v1", api_key_env="ORGBRAIN_TEST_KEY"))
    monkeypatch.setenv("ORGBRAIN_TEST_KEY", "k")
    assert (await rs.set(RuntimeConfig(runtime="api", base_url="https://x/v1", api_key_env="ORGBRAIN_TEST_KEY"))).runtime == "api"
    assert await rs.get() != RuntimeConfig()


@pytest.mark.anyio
async def test_runtime_is_built_once_per_config():
    calls = []
    rs = await settings(lambda cfg: calls.append(cfg) or f"rt-{cfg.effort}")
    assert await rs.runtime() == await rs.runtime() == "rt-low" and len(calls) == 1
    await rs.set(RuntimeConfig(effort="high"))
    assert await rs.runtime() == "rt-high" and len(calls) == 2
