"""Deterministic random data generation for tests.

Every generator is seeded (a fixed default seed is used unless overridden)
so failures are reproducible. Prices follow a seeded random walk so the
generated OHLC values are internally consistent.
"""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.marketdata.models import OrderBookEvent, OrderBookLevel, TickerEvent, TradeEvent

DEFAULT_SEED = 20260101


def seeded_rng(seed: int = DEFAULT_SEED) -> random.Random:
    """Return a reproducible random generator."""
    return random.Random(seed)


def random_price(rng: random.Random, base: Decimal, spread: Decimal) -> Decimal:
    """A price within ``±spread`` of ``base`` with two decimal places."""
    offset = Decimal(str(rng.uniform(-1.0, 1.0))) * spread
    return (base + offset).quantize(Decimal("0.01"))


def random_candle_row(
    rng: random.Random,
    open_time: datetime,
    timeframe: str = "1h",
    *,
    base: Decimal = Decimal("3000"),
    source: str = "delta",
) -> dict[str, Any]:
    """A single internally-consistent OHLCV row for the given bucket start."""
    span = {"1h": timedelta(hours=1), "5m": timedelta(minutes=5), "1d": timedelta(days=1)}[
        timeframe
    ]
    open_price = random_price(rng, base, Decimal("200"))
    close_price = random_price(rng, base, Decimal("200"))
    high = max(open_price, close_price) + Decimal(str(rng.uniform(0, 10))).quantize(Decimal("0.01"))
    low = min(open_price, close_price) - Decimal(str(rng.uniform(0, 10))).quantize(Decimal("0.01"))
    return {
        "timeframe": timeframe,
        "open_time": open_time,
        "close_time": open_time + span,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close_price,
        "volume": Decimal(str(rng.uniform(1, 1000))).quantize(Decimal("0.1")),
        "quote_volume": None,
        "trade_count": rng.randint(1, 500),
        "source": source,
    }


def random_candle_rows(
    count: int,
    start: datetime | None = None,
    timeframe: str = "1h",
    *,
    seed: int = DEFAULT_SEED,
    step: timedelta | None = None,
) -> list[dict[str, Any]]:
    """A consecutive run of ``count`` candle rows starting at ``start``."""
    rng = seeded_rng(seed)
    start = start or datetime(2026, 1, 1, tzinfo=UTC)
    step = step or timedelta(hours={"5m": 5 / 60, "1h": 1, "1d": 24}[timeframe])
    return [random_candle_row(rng, start + i * step, timeframe) for i in range(count)]


def random_trade_event(
    symbol: str = "ETHUSD",
    *,
    seed: int = DEFAULT_SEED,
    event_time: datetime | None = None,
) -> TradeEvent:
    """A deterministic trade event."""
    rng = seeded_rng(seed)
    return TradeEvent(
        exchange="delta",
        symbol=symbol,
        event_time=event_time or datetime(2026, 1, 1, tzinfo=UTC),
        side=rng.choice(["buy", "sell"]),
        price=random_price(rng, Decimal("3000"), Decimal("50")),
        size=Decimal(str(rng.uniform(0.01, 10))).quantize(Decimal("0.001")),
    )


def random_ticker_event(
    symbol: str = "ETHUSD",
    *,
    seed: int = DEFAULT_SEED,
    event_time: datetime | None = None,
) -> TickerEvent:
    """A deterministic ticker event with a realistic top of book."""
    rng = seeded_rng(seed)
    mid = random_price(rng, Decimal("3000"), Decimal("100"))
    return TickerEvent(
        exchange="delta",
        symbol=symbol,
        event_time=event_time or datetime(2026, 1, 1, tzinfo=UTC),
        bid=mid - Decimal("0.5"),
        ask=mid + Decimal("0.5"),
        bid_size=Decimal(str(rng.uniform(1, 50))).quantize(Decimal("0.1")),
        ask_size=Decimal(str(rng.uniform(1, 50))).quantize(Decimal("0.1")),
        last_price=mid,
        mark_price=mid,
        price_change_24h=Decimal(str(rng.uniform(-5, 5))).quantize(Decimal("0.01")),
        turnover=Decimal(str(rng.uniform(1000, 100000))).quantize(Decimal("0.01")),
    )


def random_order_book_event(
    symbol: str = "ETHUSD",
    *,
    seed: int = DEFAULT_SEED,
    event_time: datetime | None = None,
    levels: int = 5,
) -> OrderBookEvent:
    """A deterministic L2 order book snapshot around a random mid price."""
    rng = seeded_rng(seed)
    mid = random_price(rng, Decimal("3000"), Decimal("100"))
    bids: list[OrderBookLevel] = []
    asks: list[OrderBookLevel] = []
    for i in range(levels):
        bids.append(
            OrderBookLevel(
                price=(mid - Decimal(str(i + 1))).quantize(Decimal("0.01")),
                size=Decimal(str(rng.uniform(0.1, 20))).quantize(Decimal("0.1")),
            )
        )
        asks.append(
            OrderBookLevel(
                price=(mid + Decimal(str(i + 1))).quantize(Decimal("0.01")),
                size=Decimal(str(rng.uniform(0.1, 20))).quantize(Decimal("0.1")),
            )
        )
    return OrderBookEvent(
        exchange="delta",
        symbol=symbol,
        event_time=event_time or datetime(2026, 1, 1, tzinfo=UTC),
        kind="l2",
        bids=bids,
        asks=asks,
        is_snapshot=True,
    )
