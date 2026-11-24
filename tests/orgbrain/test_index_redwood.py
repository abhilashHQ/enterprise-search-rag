import numpy as np

from orgbrain.config import Settings
from orgbrain.index_redwood import read_bm25_stats, write_bm25_stats


def test_bm25_stats_round_trip(tmp_path):
    p = tmp_path / "bm25.json"
    assert write_bm25_stats(p, np.array([2, 4, 6])) == {"avgdl": 4.0, "n_docs": 3}
    assert read_bm25_stats(p) == {"avgdl": 4.0, "n_docs": 3}


def test_settings_have_redis_and_bm25_stats(monkeypatch, tmp_path):
    monkeypatch.setenv("ORGBRAIN_REDIS_URL", "redis://h:1/2")
    monkeypatch.setenv("ORGBRAIN_BM25_STATS_PATH", str(tmp_path / "s.json"))
    s = Settings.from_env()
    assert s.redis_url == "redis://h:1/2" and s.bm25_stats_path == tmp_path / "s.json"
