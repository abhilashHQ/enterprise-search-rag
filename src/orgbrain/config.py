import os
from dataclasses import dataclass, fields

ENV = {"qdrant_url": "ORGBRAIN_QDRANT_URL", "models_url": "ORGBRAIN_MODELS_URL", "database_url": "ORGBRAIN_DATABASE_URL"}


@dataclass(frozen=True)
class Settings:
    qdrant_url: str = "http://127.0.0.1:6333"
    models_url: str = "http://127.0.0.1:8766"
    database_url: str = "postgresql+asyncpg://orgbrain:orgbrain@127.0.0.1:5432/orgbrain"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(**{f.name: os.environ[ENV[f.name]] for f in fields(cls) if ENV[f.name] in os.environ})
