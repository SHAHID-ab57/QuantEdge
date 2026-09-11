"""Unit tests for the live market (ticker + funding) assembly service."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.events.bus import EventBus
from app.integrations.delta.exceptions import NetworkError
from app.integrations.delta.models import DeltaTicker
from app.marketdata.bus_events import FundingRateUpdated, TickerUpdated
from app.marketdata.models import FundingRateEvent, TickerEvent
from app.services.live_market import LiveMarketService
from app.state.manager import MarketStateManager

pytestmark = pytest.mark.asyncio


def ticker(**overrides: object) -> TickerEvent:
    base: dict[str, object] = {
        "exchange": "delta",
        "symbol": "ETHUSD",
        "event_time": datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        "last_price": Decimal("2465.7"),
        "bid": Decimal("2465.65"),
        "ask": Decimal("2465.70"),
        "mark_price": Decimal("2465.66"),
        "open_interest": Decimal("17934.2"),
        "price_change_24h": Decimal("0.0507"),
        "turnover": Decimal("710726972.59"),
    }
    base.update(overrides)
    return TickerEvent(**base)  # type: ignore[arg-type]


def funding(**overrides: object) -> FundingRateEvent:
    base: dict[str, object] = {
        "exchange": "delta",
        "symbol": "ETHUSD",
        "event_time": datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        "funding_rate": Decimal("-0.001156"),
        "funding_interval_seconds": 28800,
        "next_funding_time": datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return FundingRateEvent(**base)  # type: ignore[arg-type]


class _StubDelta:
    def __init__(self, result: DeltaTicker | Exception) -> None:
        self._result = result
        self.calls = 0

    async def get_ticker(self, symbol: str) -> DeltaTicker:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


async def _populated_manager(*events: object) -> MarketStateManager:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)
    for event in events:
        await bus.publish(event)  # type: ignore[arg-type]
    await bus.drain()
    return manager


async def test_empty_state_yields_all_null_source_none() -> None:
    manager = MarketStateManager()
    service = LiveMarketService(state_manager=manager)

    response = await service.get_ticker("ethusd")

    assert response.symbol == "ETHUSD"
    assert response.source == "none"
    assert response.last_price is None
    assert response.funding_rate is None


async def test_ws_ticker_and_funding_are_merged() -> None:
    manager = await _populated_manager(
        TickerUpdated(source="t", ticker=ticker()),
        FundingRateUpdated(source="t", funding_rate=funding()),
    )
    service = LiveMarketService(state_manager=manager, delta_client=_StubDelta(NetworkError("x")))  # type: ignore[arg-type]

    response = await service.get_ticker("ETHUSD")

    assert response.source == "ws"
    assert response.last_price == Decimal("2465.7")
    assert response.open_interest == Decimal("17934.2")
    assert response.funding_rate == Decimal("-0.001156")
    assert response.funding_interval_seconds == 28800


async def test_rest_fills_in_missing_funding_and_open_interest() -> None:
    manager = await _populated_manager(
        TickerUpdated(source="t", ticker=ticker(open_interest=None)),
    )
    stub = _StubDelta(
        DeltaTicker(
            symbol="ETHUSD",
            funding_rate=Decimal("-0.001156"),
            oi=Decimal("17934.2"),
            oi_contracts=Decimal("1793420"),
            spot_price=Decimal("2466.72"),
        )
    )
    service = LiveMarketService(state_manager=manager, delta_client=stub)  # type: ignore[arg-type]

    response = await service.get_ticker("ETHUSD")

    assert stub.calls == 1
    assert response.source == "rest"
    assert response.funding_rate == Decimal("-0.001156")
    # Prefers `oi_contracts` to match the WS ticker channel's units.
    assert response.open_interest == Decimal("1793420")
    assert response.spot_price == Decimal("2466.72")


async def test_rest_failure_is_swallowed() -> None:
    manager = await _populated_manager(
        TickerUpdated(source="t", ticker=ticker(open_interest=None)),
    )
    stub = _StubDelta(NetworkError("delta down"))
    service = LiveMarketService(state_manager=manager, delta_client=stub)  # type: ignore[arg-type]

    response = await service.get_ticker("ETHUSD")

    assert stub.calls == 1
    assert response.source == "none"
    assert response.funding_rate is None
    assert response.last_price == Decimal("2465.7")


async def test_no_rest_call_when_ws_already_has_funding_and_oi() -> None:
    manager = await _populated_manager(
        TickerUpdated(source="t", ticker=ticker()),
        FundingRateUpdated(source="t", funding_rate=funding()),
    )
    stub = _StubDelta(NetworkError("should not be called"))
    service = LiveMarketService(state_manager=manager, delta_client=stub)  # type: ignore[arg-type]

    await service.get_ticker("ETHUSD")

    assert stub.calls == 0
