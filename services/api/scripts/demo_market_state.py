"""Offline demo of the market state manager.

Creates an event bus, registers the MarketStateManager, publishes mock
normalized events (trade, ticker, order book, candle), and prints the
market state after each event to show that the latest state is
maintained (state replacement, per-resolution candles, multi-symbol
isolation).

No network access is required.

Usage:
    uv run python scripts/demo_market_state.py
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal

from app.core.logging import setup_logging
from app.events import CandleClosed, Event, EventBus
from app.marketdata import (
    OrderBookUpdated,
    TickerUpdated,
    TradeEventReceived,
)
from app.marketdata.models import OrderBookEvent, OrderBookLevel, TickerEvent, TradeEvent
from app.state import MarketState, MarketStateManager


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line argument parser."""
    return argparse.ArgumentParser(
        description="Demo the market state manager with mock events (offline)."
    )


def make_trade(symbol: str, price: str, size: str = "1.5") -> TradeEventReceived:
    return TradeEventReceived(
        source="demo",
        trade=TradeEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            price=Decimal(price),
            size=Decimal(size),
            side="unknown",
        ),
    )


def make_ticker(symbol: str, bid: str, ask: str) -> TickerUpdated:
    return TickerUpdated(
        source="demo",
        ticker=TickerEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            bid=Decimal(bid),
            ask=Decimal(ask),
        ),
    )


def make_book(symbol: str, best_bid: str, best_ask: str) -> OrderBookUpdated:
    return OrderBookUpdated(
        source="demo",
        order_book=OrderBookEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            kind="l1",
            bids=[OrderBookLevel(price=Decimal(best_bid), size=Decimal("2.5"))],
            asks=[OrderBookLevel(price=Decimal(best_ask), size=Decimal("3.0"))],
            is_snapshot=True,
        ),
    )


def make_candle(symbol: str, resolution: str, close: str) -> CandleClosed:
    return CandleClosed(
        source="demo",
        symbol=symbol,
        resolution=resolution,
        open=Decimal("71000"),
        high=Decimal("72000"),
        low=Decimal("70900"),
        close=Decimal(close),
        volume=Decimal("100"),
    )


def format_state(state: MarketState | None) -> str:
    """One-line summary of a market state snapshot."""
    if state is None:
        return "  (no state recorded)"
    lines = [
        f"  updated_at : {state.updated_at.astimezone(UTC).strftime('%H:%M:%S.%f')[:-3]} UTC",
    ]
    if state.trade is not None:
        trade = state.trade
        lines.append(f"  trade      : price={trade.price} size={trade.size} side={trade.side}")
    else:
        lines.append("  trade      : (none)")
    if state.ticker is not None:
        ticker = state.ticker
        lines.append(f"  ticker     : bid={ticker.bid} ask={ticker.ask} last={ticker.last_price}")
    else:
        lines.append("  ticker     : (none)")
    if state.order_book is not None:
        book = state.order_book
        lines.append(
            f"  order book : kind={book.kind} bids={len(book.bids)} "
            f"asks={len(book.asks)} snapshot={book.is_snapshot}"
        )
    else:
        lines.append("  order book : (none)")
    if state.candle is not None:
        candle = state.candle
        lines.append(
            f"  candle     : {candle.resolution} close={candle.close} volume={candle.volume}"
        )
    else:
        lines.append("  candle     : (none)")
    if state.last_price is not None:
        lines.append(f"  last price : {state.last_price}")
    return "\n".join(lines)


async def publish(
    bus: EventBus,
    manager: MarketStateManager,
    event: Event,
    symbol: str,
    label: str,
) -> None:
    """Publish one event, drain handlers, and print the resulting state."""
    print(f"\n>>> {label}", flush=True)
    await bus.publish(event)
    await bus.drain()
    print(format_state(manager.get_market_state(symbol)), flush=True)


async def run(args: argparse.Namespace) -> int:
    """Run the offline state manager demo."""
    bus = EventBus()
    manager = MarketStateManager().attach(bus)
    print("MarketStateManager registered on EventBus", flush=True)

    await publish(
        bus,
        manager,
        make_trade("BTCUSD", "72141.5"),
        "BTCUSD",
        "Publish trade BTCUSD 72141.5",
    )
    await publish(
        bus,
        manager,
        make_ticker("BTCUSD", "72141.0", "72142.0"),
        "BTCUSD",
        "Publish ticker BTCUSD bid=72141.0 ask=72142.0",
    )
    await publish(
        bus,
        manager,
        make_book("BTCUSD", "72141.5", "72142.0"),
        "BTCUSD",
        "Publish order book BTCUSD (l1)",
    )
    await publish(
        bus,
        manager,
        make_candle("BTCUSD", "1h", "71500"),
        "BTCUSD",
        "Publish candle BTCUSD 1h close=71500",
    )
    await publish(
        bus,
        manager,
        make_trade("BTCUSD", "72200.0"),
        "BTCUSD",
        "Publish NEWER trade BTCUSD 72200.0 (state replacement)",
    )

    print("\n--- Final market state per symbol ---", flush=True)
    for symbol in sorted(manager.symbols()):
        print(f"{symbol}:", flush=True)
        print(format_state(manager.get_market_state(symbol)), flush=True)

    metrics = manager.metrics.snapshot()
    print("\n--- StateMetrics ---", flush=True)
    for key, value in metrics.items():
        print(f"  {key}: {value}", flush=True)

    latest = manager.get_latest_trade("BTCUSD")
    ok = (
        latest is not None
        and latest.price == Decimal("72200.0")
        and manager.get_latest_candle("BTCUSD", "1h") is not None
        and metrics["state_updates"] == 5
    )
    print("\n=== VERDICT: PASS ===" if ok else "\n=== VERDICT: FAIL ===", flush=True)
    return 0 if ok else 1


def main() -> int:
    """Entry point."""
    setup_logging()
    args = build_parser().parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
