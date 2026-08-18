"""Live end-to-end demo of the market data pipeline.

Connects to the Delta public WebSocket socket, streams real market data
through the full pipeline, and verifies each stage:

1. Raw Delta WebSocket messages are received by the client.
2. They pass through ``MarketDataPipeline.handle`` (client listener).
3. ``DeltaNormalizer`` converts them to domain events.
4. Domain events are published on the ``EventBus``.
5. ``LoggingHandler`` receives them (logged at INFO).
6. ``ProcessingMetrics`` are printed at the end with a pass/fail verdict.

Uses only the public client API (``start``/``run``/``close``/``subscribe``/
``add_listener``) — no context manager, no client modifications.

Usage:
    uv run python scripts/marketdata_demo.py --duration 15
    uv run python scripts/marketdata_demo.py --symbols BTCUSD --channels trades,ticker,ob_l1
"""

import argparse
import asyncio
import logging
import signal
import sys
from asyncio import CancelledError
from contextlib import suppress

from app.core.logging import setup_logging
from app.events import EventBus, LoggingHandler
from app.integrations.delta.websocket.client import get_delta_ws_client
from app.marketdata import DeltaNormalizer, MarketDataPipeline

logger = logging.getLogger(__name__)

_DESCRIPTION = "Stream live Delta market data through the pipeline and print metrics."


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line argument parser."""
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument(
        "--duration",
        type=float,
        default=15.0,
        help="seconds to stream (default 15)",
    )
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
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    return parser


def run_pipeline(bus: EventBus) -> MarketDataPipeline:
    """Build the pipeline and wire its listeners to logging."""
    pipeline = MarketDataPipeline(normalizer=DeltaNormalizer(), bus=bus)
    for event_type in ("TradeEventReceived", "TickerUpdated", "OrderBookUpdated"):
        bus.subscribe(event_type, LoggingHandler())
    return pipeline


async def run(args: argparse.Namespace) -> int:
    """Stream for ``args.duration`` seconds and report metrics."""
    bus = EventBus()
    pipeline = run_pipeline(bus)

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
    run_task = asyncio.create_task(client.run(), name="marketdata-demo-run")
    stop_waiter = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait(
        {stop_waiter, run_task}, return_when=asyncio.FIRST_COMPLETED
    )
    await client.close()
    stop_waiter.cancel()
    with suppress(CancelledError):
        await stop_waiter
    if run_task in done:
        logger.warning("WebSocket run loop ended; no more reconnects will be attempted")
    await bus.drain()

    metrics = pipeline.metrics.snapshot()
    print("\n=== Market data pipeline metrics ===", flush=True)
    for key, value in metrics.items():
        print(f"  {key}: {value}", flush=True)
    if metrics["messages_received"] == 0:
        print(
            "  (note: messages_received counts raw frames via process_raw; "
            "this demo uses the client listener path, so normalized/published "
            "are the live counters)",
            flush=True,
        )
    ok = bool(metrics["events_published"]) and metrics["validation_failures"] == 0
    print("=== VERDICT: PASS ===" if ok else "=== VERDICT: FAIL ===", flush=True)
    return 0 if ok else 1


def main() -> int:
    """Entry point."""
    setup_logging()
    args = build_parser().parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())