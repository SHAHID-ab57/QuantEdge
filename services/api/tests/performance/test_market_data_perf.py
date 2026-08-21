"""Performance smoke tests with generous, flake-resistant timing budgets.

Marked ``performance`` and skipped unless ``--run-performance`` is passed
(``make test-performance``). The primary assertions are correctness; the
timing budgets are intentionally loose — they exist to catch catastrophic
regressions (quadratic pagination, unbounded handler latency), not to
benchmark the machine.
"""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.events import EventBus
from app.marketdata import MarketDataPipeline
from app.marketdata.bus_events import TradeEventReceived
from app.marketdata.normalizer import DeltaNormalizer
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.services.market_data import MarketDataService
from tests.helpers.factories import seed_market_with_candles
from tests.helpers.generators import random_candle_rows, random_trade_event

pytestmark = pytest.mark.performance

PAGINATION_PAGES = 50
PAGINATION_PAGE_SIZE = 100
PAGINATION_CANDLES = PAGINATION_PAGES * PAGINATION_PAGE_SIZE

EVENT_COUNT = 2000
PIPELINE_MESSAGES = 1000

PAGINATION_BUDGET_S = 15.0
BUS_BUDGET_S = 10.0
PIPELINE_BUDGET_S = 15.0

VALID_TRADE = json.dumps(
    {
        "type": "trades",
        "p": "72141.5",
        "r": "t",
        "s": "1.5",
        "sy": "BTCUSD",
        "t": 1700000000000000,
        "ts": 1700000000005000,
    }
)


async def test_pagination_walk_budget(
    session_factory,
) -> None:
    """Walking 50 pages of 100 candles stays contiguous and within budget."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = random_candle_rows(
        PAGINATION_CANDLES,
        start=start,
        timeframe="1h",
        step=timedelta(hours=1),
        seed=7,
    )
    await seed_market_with_candles(session_factory, rows, symbol="PERFUSD")

    service = MarketDataService(
        candle_repository=CandleRepository(session_factory()),
        market_repository=MarketRepository(session_factory()),
        default_limit=100,
        max_limit=1000,
    )
    began = time.perf_counter()
    previous_close_time = None
    total = 0
    for page in range(PAGINATION_PAGES):
        result = await service.get_candles(
            symbol="PERFUSD",
            timeframe="1h",
            limit=PAGINATION_PAGE_SIZE,
            offset=page * PAGINATION_PAGE_SIZE,
        )
        assert result.items, f"page {page} returned no candles"
        for candle in result.items:
            if previous_close_time is not None:
                assert candle.open_time == previous_close_time, "gap in pagination walk"
            previous_close_time = candle.close_time
        total += len(result.items)
    elapsed = time.perf_counter() - began

    assert total == PAGINATION_CANDLES
    assert elapsed < PAGINATION_BUDGET_S, f"pagination walk took {elapsed:.2f}s"


async def test_event_bus_throughput_budget(event_bus: EventBus) -> None:
    """Publishing 2000 events to one handler stays within budget."""
    handled: list[int] = []

    async def handler(event: object) -> None:
        handled.append(1)

    event_bus.subscribe("TradeEventReceived", handler)
    began = time.perf_counter()
    for _ in range(EVENT_COUNT):
        event = TradeEventReceived(
            source="perf",
            trade=random_trade_event(seed=1),
        )
        await event_bus.publish(event)
    await event_bus.drain()
    elapsed = time.perf_counter() - began

    assert len(handled) == EVENT_COUNT
    assert event_bus.published_events == EVENT_COUNT
    assert event_bus.failed_handlers == 0
    assert elapsed < BUS_BUDGET_S, f"event bus took {elapsed:.2f}s"


async def test_pipeline_throughput_budget(event_bus: EventBus) -> None:
    """1000 raw messages through the full pipeline stay within budget."""
    pipeline = MarketDataPipeline(normalizer=DeltaNormalizer(), bus=event_bus)
    began = time.perf_counter()
    for _ in range(PIPELINE_MESSAGES):
        await pipeline.process_raw(VALID_TRADE)
    await event_bus.drain()
    elapsed = time.perf_counter() - began

    assert pipeline.metrics.messages_received == PIPELINE_MESSAGES
    assert pipeline.metrics.validation_failures == 0
    assert event_bus.published_events == PIPELINE_MESSAGES
    assert elapsed < PIPELINE_BUDGET_S, f"pipeline took {elapsed:.2f}s"


async def test_seeding_five_thousand_candles_is_fast(
    session_factory,
) -> None:
    """Bulk-seeding 5000 candles (the perf fixture) stays fast."""
    rows = random_candle_rows(
        5000,
        start=datetime(2024, 1, 1, tzinfo=UTC),
        timeframe="1h",
        seed=7,
    )
    began = time.perf_counter()
    market_id = await seed_market_with_candles(
        session_factory, rows, symbol="SEEDUSD"
    )
    elapsed = time.perf_counter() - began

    assert market_id is not None
    assert elapsed < 30.0, f"seeding took {elapsed:.2f}s"