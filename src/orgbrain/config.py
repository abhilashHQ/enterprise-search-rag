import os
from dataclasses import dataclass, fields
from pathlib import Path

from entsearch.data import ROOT

ENV = {"qdrant_url": "ORGBRAIN_QDRANT_URL", "models_url": "ORGBRAIN_MODELS_URL", "database_url": "ORGBRAIN_DATABASE_URL",
       "fts_path": "ORGBRAIN_FTS_PATH", "docstore_path": "ORGBRAIN_DOCSTORE_PATH", "redis_url": "ORGBRAIN_REDIS_URL",
       "bm25_stats_path": "ORGBRAIN_BM25_STATS_PATH"}


@dataclass(frozen=True)
class Settings:
    qdrant_url: str = "http://127.0.0.1:6333"
    models_url: str = "http://127.0.0.1:8766"
    database_url: str = "postgresql+asyncpg://orgbrain:orgbrain@127.0.0.1:5432/orgbrain"
    fts_path: Path = ROOT / "data/index/fts.sqlite"
    docstore_path: Path = ROOT / "data/index/docstore.sqlite"
    redis_url: str = "redis://127.0.0.1:6379/0"
    bm25_stats_path: Path = ROOT / "data/index/bm25.json"

    @classmethod
    def from_env(cls) -> "Settings":
        env = {f.name: os.environ[ENV[f.name]] for f in fields(cls) if ENV[f.name] in os.environ}
        return cls(**{k: Path(v) if k.endswith("_path") else v for k, v in env.items()})
