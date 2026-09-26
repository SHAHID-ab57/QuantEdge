"""Fixtures for `tests/monitoring/` — capture what error tracking would
send, and what logging would print, so both are asserted on directly.
"""

import io
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app.core.config import Settings
from app.core.logging import configure_logging
from app.monitoring.error_tracking import init_error_tracking

DSN = "https://public@example.invalid/1"


class CaptureTransport(Transport):
    """Records every envelope the SDK would have sent over the network."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.envelopes: list[Envelope] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)


@dataclass
class Tracker:
    transport: CaptureTransport
    settings: Settings = field(default_factory=lambda: Settings(sentry_dsn=DSN))

    @property
    def events(self) -> list[dict[str, Any]]:
        """Every error event that would have been sent, as its wire JSON."""
        found = []
        for envelope in self.transport.envelopes:
            for item in envelope.items:
                if item.headers.get("type") == "event":
                    found.append(item.payload.json)
        return found

    @property
    def wire_text(self) -> str:
        """Everything that would have left the process, as one string."""
        import json

        return json.dumps(self.events, default=str)


@pytest.fixture
def tracker() -> Iterator[Tracker]:
    """Real SDK initialization (`init_error_tracking`), in-process transport."""
    transport = CaptureTransport()
    settings = Settings(sentry_dsn=DSN, app_env="test", jwt_secret_key="unit-test-secret")
    assert init_error_tracking(settings, transport=transport) is True
    # Belt and braces: whatever an earlier test left on the SDK's shared
    # scopes must not colour this test's events.
    for scope in (
        sentry_sdk.get_global_scope(),
        sentry_sdk.get_isolation_scope(),
        sentry_sdk.get_current_scope(),
    ):
        scope.clear()
    yield Tracker(transport, settings)
    sentry_sdk.init()  # back to a disabled client (SENTRY_DSN is forced empty)


@pytest.fixture
def json_logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """The app's real JSON log handler, writing to an in-memory stream.

    `setup_logging` is pinned as already-done: an app lifespan started
    inside a test would otherwise reconfigure logging to stderr and
    replace this handler.
    """
    monkeypatch.setattr("app.core.logging._configured", True)
    stream = io.StringIO()
    handler = configure_logging(level="INFO", log_format="json", stream=stream)
    yield stream
    logging.getLogger().removeHandler(handler)
