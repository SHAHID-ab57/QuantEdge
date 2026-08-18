"""Inspect the in-memory market state of the running pipeline.

Connects to the Delta public socket, feeds real messages through the
market data pipeline into the MarketStateManager, and prints the
current per-symbol state on a refresh interval.

The state is process-local: this script builds and owns the manager, so
it shows exactly what a consumer would see inside the same process.

Usage:
    uv run python scripts/show_market_state.py --symbols BTCUSD,ETHUSD
    uv run python scripts/show_market_state.py --duration 30 --refresh 5
"""

import argparse
import asyncio
import logging
import signal
import sys
from asyncio import CancelledError
from contextlib import suppress
from datetime import UTC

from app.core.logging import setup_logging
from app.events import EventBus
from app.integrations.delta.websocket.client import get_delta_ws_client
from app.marketdata import DeltaNormalizer, MarketDataPipeline
from app.state import MarketState, MarketStateManager

logger = logging.getLogger(__name__)

_DESCRIPTION = "Stream live Delta market data and print the in-memory market state."


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line argument parser."""
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument(
        "--symbols",
        default="BTCUSD,ETHUSD",
        help="comma-separated symbols (default BTCUSD,ETHUSD)",
    )
    parser.add_argument(
        "--channels",
        default="trades,ticker,ob_l1",
        help="comma-separated Delta channels (default trades,ticker,ob_l1)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=15.0,
        help="seconds to run (default 15)",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=2.0,
        help="seconds between state prints (default 2)",
    )
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    return parser


def format_state(symbol: str, state: MarketState | None) -> str:
    """One-line summary of a market state snapshot."""
    if state is None:
        return f"{symbol}: (no state yet)"
    parts = [
        symbol,
        state.updated_at.astimezone(UTC).strftime("%H:%M:%S.%f")[:-3],
    ]
    if state.trade is not None:
        parts.append(f"trade={state.trade.price}")
    if state.ticker is not None:
        ticker = state.ticker
        parts.append(f"bid={ticker.bid}")
        parts.append(f"ask={ticker.ask}")
        if ticker.last_price is not None:
            parts.append(f"last={ticker.last_price}")
    if state.order_book is not None:
        book = state.order_book
        parts.append(f"book={book.kind}/{len(book.bids)}b/{len(book.asks)}a")
    if state.candle is not None:
        parts.append(f"candle={state.candle.resolution}:{state.candle.close}")
    return " | ".join(parts)


async def run(args: argparse.Namespace) -> int:
    """Stream live data and print state every ``--refresh`` seconds."""
    bus = EventBus()
    manager = MarketStateManager().attach(bus)
    pipeline = MarketDataPipeline(normalizer=DeltaNormalizer(), bus=bus)

    client = get_delta_ws_client()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or None
    channels = [c.strip() for c in args.channels.split(",") if c.strip()]
    for channel in channels:
        client.add_listener(channel, pipeline.handle)
        await client.subscribe(channel, symbols)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, stop.set)
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    loop.call_later(args.duration, stop.set)

    client.start()
    run_task = asyncio.create_task(client.run(), name="show-market-state-run")
    while not stop.is_set():
        print("--- market state ---", flush=True)
        for symbol in sorted(manager.symbols()):
            print(format_state(symbol, manager.get_market_state(symbol)), flush=True)
        if not manager.symbols():
            print("(waiting for the first events...)", flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=args.refresh)
        except TimeoutError:
            continue
    await client.close()
    if not run_task.done():
        run_task.cancel()
        with suppress(CancelledError):
            await run_task
    await bus.drain()

    metrics = manager.metrics.snapshot()
    print("\n--- StateMetrics ---", flush=True)
    for key, value in metrics.items():
        print(f"  {key}: {value}", flush=True)
    return 0


def main() -> int:
    """Entry point."""
    setup_logging()
    args = build_parser().parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())