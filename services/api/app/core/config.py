"""Application configuration.

Configuration is loaded from environment variables and an optional .env file.
All future services must follow the conventions in configs/README.md.
Database variables follow the catalog in configs/environment.example.md.
"""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "eth-ai-api"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "DB_URL"),
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    candles_default_limit: int = 100
    candles_max_limit: int = 1000

    experiments_default_limit: int = 50
    experiments_max_limit: int = 200

    training_jobs_default_limit: int = 50
    training_jobs_max_limit: int = 200

    ml_dataset_builds_default_limit: int = 20
    ml_dataset_builds_max_limit: int = 100

    #: How many completed training jobs a single benchmark comparison
    #: (`app/services/evaluation.py`) will ever fetch and compare at once —
    #: a benchmark has no page/offset concept of its own, so this is a flat
    #: cap rather than a default/max pair.
    evaluation_benchmark_max_candidates: int = 100

    #: Benchmark History's list pagination — every successful benchmark
    #: comparison is recorded (best-effort), and this bounds how many past
    #: runs `GET /evaluation/history` returns per page.
    evaluation_history_default_limit: int = 20
    evaluation_history_max_limit: int = 100

    #: Where fitted baseline model artifacts are serialized to (joblib), relative
    #: to the service's working directory unless given as an absolute path.
    model_artifact_dir: str = "var/model_artifacts"

    delta_base_url: str = "https://api.india.delta.exchange"
    delta_api_key: str = ""
    delta_api_secret: str = ""
    delta_request_timeout: float = 10.0

    delta_ws_url: str = "wss://public-socket.india.delta.exchange"
    delta_ws_private_url: str = "wss://socket.india.delta.exchange"
    delta_ws_reconnect_delay: float = 2.0
    delta_ws_max_retries: int = 0

    market_data_live: bool = False
    delta_market_symbols: str = "BTCUSD,ETHUSD"

    candle_sync_enabled: bool = True
    candle_sync_interval_seconds: int = 300
    candle_sync_timeframes: str = "1m,5m,15m,30m,1h,4h,1d"
    candle_sync_symbols: str = ""
    candle_sync_backfill_days: int = 7


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
