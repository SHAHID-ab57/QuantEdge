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
    cors_origins: list[str] = []

    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "DB_URL"),
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
