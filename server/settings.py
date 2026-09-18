"""Central configuration for the Stockfish service (env-driven)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    stockfish_path: str = "stockfish"
    engine_max_concurrent: int = 2
    engine_timeout_s: float = 30.0
    engine_cache_size: int = 512
    engine_cache_ttl_s: float = 3600.0
    engine_threads: int = 1
    engine_hash_mb: int = 128
    engine_skill_default: int = 20  # kept at full strength; reserved for future handicap modes
    max_depth: int = 28
    max_multipv: int = 5
    cors_origins: str = "http://localhost:5173"
    rate_limit_per_min: int = 60
    app_version: str = "0.2.0"


settings = Settings()
