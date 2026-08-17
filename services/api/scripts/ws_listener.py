"""Command-line listener for Delta Exchange WebSocket market data.

Connects to the Delta WebSocket API, subscribes to the requested
channels, and prints every parsed event until interrupted (or for a
fixed ``--duration``).

By default it connects to the public socket (no credentials needed);
``--private`` switches to the private socket, which requires
``DELTA_API_KEY`` / ``DELTA_API_SECRET`` for ``key-auth``.

Usage:
    uv run python scripts/ws_listener.py --channel ticker=ETHUSD,BTCUSD
    uv run python scripts/ws_listener.py --channel trades=ETHUSD --duration 60

Channels are specified as ``NAME`` (whole channel) or ``NAME=SYM1,SYM2``
(specific symbols), repeatable, e.g. ``--channel ticker=ETHUSD``
``--channel funding_rate``.
"""

import argparse
import asyncio
import logging
import signal
import sys
from asyncio import CancelledError
from contextlib import suppress

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.integrations.delta.websocket.client import DeltaWebSocketClient
from app.ws.config import WebSocketSettings
from app.ws.models import WSEvent

logger = logging.getLogger(__name__)

_DESCRIPTION = "Listen to Delta Exchange WebSocket market data and print events."


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line argument parser."""
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument(
        "--channel",
        action="append",
        default=[],
        metavar="NAME[=SYMBOL[,SYMBOL...]]",
        help="channel to subscribe, e.g. ticker=ETHUSD,BTCUSD (repeatable)",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="use the private socket and authenticate with API credentials",
    )
    parser.add_argument("--url", default=None, help="override the WebSocket URL")
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=None,
        help="base reconnect delay in seconds (default 2.0)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="maximum connection attempts (default 0 = unlimited)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="listen for this many seconds (default 0 = until Ctrl+C)",
    )
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    return parser


def parse_channels(specs: list[str]) -> list[tuple[str, list[str] | None]]:
    """Parse ``NAME[=SYM1,SYM2]`` specs into (channel, symbols) pairs."""
    channels = []
    for spec in specs:
        if "=" in spec:
            name, symbols_raw = spec.split("=", 1)
            symbols = [s for s in symbols_raw.split(",") if s]
            channels.append((name, symbols or None))
        else:
            channels.append((spec, None))
    return channels


def resolve_settings(args: argparse.Namespace) -> WebSocketSettings:
    """Build connection settings from CLI overrides and app settings."""
    app_settings = get_settings()
    return WebSocketSettings(
        url=(
            args.url
            or (
                app_settings.delta_ws_private_url
                if args.private
                else app_settings.delta_ws_url
            )
        ),
        reconnect_delay=(
            args.reconnect_delay
            if args.reconnect_delay is not None
            else app_settings.delta_ws_reconnect_delay
        ),
        max_retries=(
            args.max_retries
            if args.max_retries is not None
            else app_settings.delta_ws_max_retries
        ),
    )


async def print_event(event: WSEvent) -> None:
    """Print a one-line summary of an event."""
    stamp = event.received_at.strftime("%H:%M:%S")
    summary = ""
    for attr in ("sy", "symbol", "s", "channel"):
        value = getattr(event, attr, None)
        if value:
            summary = f" {value}"
            break
    print(f"[{stamp}] {event.type}{summary}", flush=True)


async def run(args: argparse.Namespace) -> int:
    """Run the listener until interrupted or the duration elapses."""
    app_settings = get_settings()
    client = DeltaWebSocketClient(
        resolve_settings(args),
        public=not args.private,
        api_key=app_settings.delta_api_key,
        api_secret=app_settings.delta_api_secret,
    )
    client.add_listener("*", print_event)
    for channel, symbols in parse_channels(args.channel):
        await client.subscribe(channel, symbols)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, stop.set)
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    if args.duration > 0:
        loop.call_later(args.duration, stop.set)

    client.start()
    run_task = asyncio.create_task(client.run(), name="ws-listener-run")
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
