"""Configuration for the Delta Exchange REST client.

Values are loaded from the central application settings (``DELTA_*``
environment variables or ``.env``) via the existing pydantic-settings system,
then validated here before the client is built.
"""

from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import get_settings


class DeltaConfig(BaseModel):
    """Immutable, validated configuration for the Delta client."""

    model_config = ConfigDict(frozen=True)

    base_url: str = "https://api.india.delta.exchange"
    api_key: str = Field(default="", repr=False)
    api_secret: str = Field(default="", repr=False)
    request_timeout: float = 10.0

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Normalize the base URL by removing a trailing slash."""
        return value.rstrip("/")

    @model_validator(mode="after")
    def _validate(self) -> "DeltaConfig":
        """Fail fast on inconsistent or unusable values."""
        if self.request_timeout <= 0:
            raise ValueError("DELTA_REQUEST_TIMEOUT must be positive")
        has_key = bool(self.api_key)
        has_secret = bool(self.api_secret)
        if has_key != has_secret:
            raise ValueError("DELTA_API_KEY and DELTA_API_SECRET must be set together")
        return self

    @classmethod
    def from_settings(cls) -> "DeltaConfig":
        """Build configuration from the central application settings."""
        settings = get_settings()
        return cls(
            base_url=settings.delta_base_url,
            api_key=settings.delta_api_key,
            api_secret=settings.delta_api_secret,
            request_timeout=settings.delta_request_timeout,
        )


@lru_cache
def get_delta_config() -> DeltaConfig:
    """Return the cached Delta client configuration."""
    return DeltaConfig.from_settings()
