"""Command-line entry point for one candle catch-up pass.

Syncs every configured market/timeframe pair up to the last closed bucket
using the same logic as the periodic scheduler. Useful for operations and
manual verification.

Usage:
    uv run python scripts/sync_candles.py
"""

import argparse
import asyncio
import sys

from app.core.logging import setup_logging
from app.services.candle_sync import run_sync_once


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Run one candle catch-up synchronization pass.",
    )
    parser.add_argument(
        "--symbols",
        help="Comma-separated symbols (defaults to candle_sync_symbols / delta_market_symbols)",
    )
    parser.add_argument(
        "--timeframes",
        help="Comma-separated timeframes (defaults to candle_sync_timeframes)",
    )
    return parser


async def _main(symbols: str | None, timeframes: str | None) -> int:
    setup_logging()
    symbol_list = [part.strip() for part in (symbols or "").split(",") if part.strip()] or None
    timeframe_list = [
        part.strip() for part in (timeframes or "").split(",") if part.strip()
    ] or None
    summary = await run_sync_once(symbols=symbol_list, timeframes=timeframe_list)
    print(
        f"attempted={summary.attempted} synced={summary.synced} "
        f"skipped={summary.skipped} failed={summary.failed} "
        f"duration={summary.duration_seconds:.2f}s"
    )
    for report in summary.reports:
        print(
            f"  {report.symbol} {report.timeframe}: received={report.received} "
            f"inserted={report.inserted} duplicates_skipped={report.duplicates_skipped} "
            f"rejected={report.rejected}"
        )
    return 0 if summary.failed == 0 else 1


def main() -> None:
    """Parse arguments and run one sync pass."""
    args = build_parser().parse_args()
    sys.exit(asyncio.run(_main(args.symbols, args.timeframes)))


if __name__ == "__main__":
    main()
