from orgbrain.config import Settings


def test_defaults_point_at_local_services():
    s = Settings()
    assert s.qdrant_url == "http://127.0.0.1:6333" and s.models_url == "http://127.0.0.1:8766"
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ORGBRAIN_QDRANT_URL", "http://q:1")
    monkeypatch.setenv("ORGBRAIN_DATABASE_URL", "sqlite+aiosqlite://")
    s = Settings.from_env()
    assert s.qdrant_url == "http://q:1" and s.database_url == "sqlite+aiosqlite://"
    assert s.models_url == Settings().models_url


def test_slack_settings(monkeypatch):
    monkeypatch.setenv("ORGBRAIN_SLACK_USERS", '{"U1": "monica.patel"}')
    monkeypatch.setenv("ORGBRAIN_PROACTIVE_PER_HOUR", "5")
    s = Settings.from_env()
    assert s.slack_user_map() == {"U1": "monica.patel"} and s.proactive_per_hour == "5"
    assert Settings().slack_user_map() == {} and Settings().api_url == "http://127.0.0.1:8000"
