"""Unit tests for the generic WebSocket connection settings."""

from dataclasses import FrozenInstanceError

import pytest

from app.ws.config import WebSocketSettings


def test_defaults_are_sane() -> None:
    """Defaults follow the Delta Exchange recommended timings."""
    settings = WebSocketSettings(url="wss://example.test")
    assert settings.reconnect_delay == 2.0
    assert settings.max_retries == 0
    assert settings.heartbeat_timeout == 35.0
    assert settings.ping_interval == 30.0
    assert settings.pong_timeout == 5.0
    assert settings.connect_timeout == 10.0
    assert settings.close_timeout == 5.0
    assert settings.max_backoff == 60.0


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("reconnect_delay", 0.0, "reconnect_delay must be positive"),
        ("reconnect_delay", -1.0, "reconnect_delay must be positive"),
        ("max_retries", -1, "max_retries must be >= 0"),
        ("heartbeat_timeout", 0.0, "heartbeat_timeout must be positive"),
        ("ping_interval", 0.0, "ping_interval must be positive"),
        ("pong_timeout", 0.0, "pong_timeout must be positive"),
        ("connect_timeout", 0.0, "connect_timeout must be positive"),
        ("close_timeout", 0.0, "close_timeout must be positive"),
        ("max_backoff", 0.0, "max_backoff must be positive"),
    ],
)
def test_invalid_values_are_rejected(
    field: str, bad_value: float | int, message: str
) -> None:
    """Non-positive timeouts and negative retries fail fast."""
    with pytest.raises(ValueError, match=message):
        kwargs = {field: bad_value}
        WebSocketSettings(url="wss://example.test", **kwargs)  # type: ignore[arg-type]


def test_frozen_and_equality() -> None:
    """Settings are immutable and compare by value."""
    a = WebSocketSettings(url="wss://a.test")
    b = WebSocketSettings(url="wss://a.test")
    c = WebSocketSettings(url="wss://c.test")
    assert a == b
    assert a != c
    with pytest.raises((FrozenInstanceError, AttributeError)):
        a.reconnect_delay = 5.0  # type: ignore[misc]