"""Tests for the example events and handlers."""

import logging
from datetime import UTC
from decimal import Decimal

import pytest

from app.events import CandleClosed, DebugHandler, EventBus, LoggingHandler


def test_candle_closed() -> None:
    event = CandleClosed(
        source="delta.ws",
        symbol="BTCUSD",
        resolution="1h",
        open=Decimal("71000"),
        high=Decimal("72141.5"),
        low=Decimal("70950"),
        close=Decimal("72000"),
        volume=Decimal("1234.5"),
    )
    assert event.event_type == "CandleClosed"
    assert event.timestamp.tzinfo == UTC
    assert event.payload == {
        "symbol": "BTCUSD",
        "resolution": "1h",
        "open": Decimal("71000"),
        "high": Decimal("72141.5"),
        "low": Decimal("70950"),
        "close": Decimal("72000"),
        "volume": Decimal("1234.5"),
    }


@pytest.mark.asyncio
async def test_logging_handler_logs_summary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    bus.subscribe("CandleClosed", LoggingHandler())
    event = CandleClosed(
        source="delta.ws",
        symbol="BTCUSD",
        resolution="1h",
        open=Decimal("71000"),
        high=Decimal("72141.5"),
        low=Decimal("70950"),
        close=Decimal("72000"),
        volume=Decimal("1234.5"),
    )
    with caplog.at_level(logging.INFO, logger="app.events"):
        await bus.publish(event)
        await bus.drain()
    assert "CandleClosed" in caplog.text


@pytest.mark.asyncio
async def test_debug_handler_logs_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    bus.subscribe("CandleClosed", DebugHandler())
    event = CandleClosed(
        source="delta.ws",
        symbol="BTCUSD",
        resolution="5m",
        open=Decimal("71000"),
        high=Decimal("71100"),
        low=Decimal("70900"),
        close=Decimal("71050"),
        volume=Decimal("100"),
    )
    with caplog.at_level(logging.DEBUG, logger="app.events"):
        await bus.publish(event)
        await bus.drain()
    assert "'resolution': '5m'" in caplog.text
