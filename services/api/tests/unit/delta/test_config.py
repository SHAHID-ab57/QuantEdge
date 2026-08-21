"""Configuration tests for the Delta client."""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.integrations.delta.config import DeltaConfig, get_delta_config


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Avoid leaking cached settings/config between tests."""
    get_settings.cache_clear()
    get_delta_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_delta_config.cache_clear()


def test_build_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """DELTA_* variables populate the DeltaConfig via application settings."""
    monkeypatch.setenv("DELTA_BASE_URL", "https://delta.local.example")
    monkeypatch.setenv("DELTA_API_KEY", "env-api-key")
    monkeypatch.setenv("DELTA_API_SECRET", "env-api-secret")
    monkeypatch.setenv("DELTA_REQUEST_TIMEOUT", "7.5")

    config = get_delta_config()

    assert config.base_url == "https://delta.local.example"
    assert config.request_timeout == 7.5
    assert config.api_key == "env-api-key"
    assert config.api_secret == "env-api-secret"


def test_defaults_without_delta_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without DELTA_* variables, documented service defaults apply."""
    Settings.model_config["env_file"] = None
    monkeypatch.setattr(Settings, "model_config", Settings.model_config)
    for name in (
        "DELTA_BASE_URL",
        "DELTA_API_KEY",
        "DELTA_API_SECRET",
        "DELTA_REQUEST_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)

    config = get_delta_config()

    assert config.base_url == "https://api.india.delta.exchange"
    assert config.request_timeout == 10.0
    assert config.api_key == ""
    assert config.api_secret == ""


def test_base_url_trailing_slash_is_stripped() -> None:
    """A trailing slash on the base URL is normalized away."""
    config = DeltaConfig(
        base_url="https://api.india.delta.exchange/",
        api_key="",
        api_secret="",
        request_timeout=5.0,
    )
    assert config.base_url == "https://api.india.delta.exchange"


def test_key_and_secret_must_be_set_together() -> None:
    """Only api_key set is invalid."""
    with pytest.raises(ValidationError):
        DeltaConfig(
            base_url="https://api.india.delta.exchange",
            api_key="only-key",
            api_secret="",
            request_timeout=5.0,
        )


def test_timeout_must_be_positive() -> None:
    """A non-positive request timeout is rejected."""
    with pytest.raises(ValidationError):
        DeltaConfig(
            base_url="https://api.india.delta.exchange",
            api_key="",
            api_secret="",
            request_timeout=0,
        )


def test_config_requires_timeout() -> None:
    """request_timeout defaults to 10 when omitted."""
    config = DeltaConfig(
        base_url="https://api.india.delta.exchange",
        api_key="",
        api_secret="",
    )
    assert config.request_timeout == 10.0


def test_repr_redacts_secrets() -> None:
    """Credentials never appear in the config repr."""
    config = DeltaConfig(
        base_url="https://api.india.delta.exchange",
        api_key="super-secret-key",
        api_secret="super-secret-secret",
        request_timeout=5.0,
    )
    text = repr(config)
    assert "super-secret-key" not in text
    assert "super-secret-secret" not in text
