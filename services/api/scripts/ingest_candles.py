"""Command-line entry point for historical OHLCV candle ingestion.

Usage:
    uv run python scripts/ingest_candles.py \
        --symbol ETHUSDT \
        --timeframe 1h \
        --start 2026-01-01 \
        --end 2026-01-31

Dates may be given as ``YYYY-MM-DD`` (midnight UTC) or as ISO datetimes
(e.g. ``2026-01-01T12:00:00``, ``2026-01-01T12:00:00Z``).
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, date, datetime, time

from app.core.logging import setup_logging
from app.services.candle_ingest import (
    DELTA_RESOLUTIONS,
    IngestReport,
    ingest_candles,
)

logger = logging.getLogger("scripts.ingest_candles")


def parse_datetime(value: str) -> datetime:
    """Parse a ``YYYY-MM-DD`` date or an ISO datetime into UTC time."""
    try:
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid datetime {value!r} (expected YYYY-MM-DD or ISO datetime)"
        ) from None


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Ingest historical OHLCV candles from Delta Exchange India.",
    )
    parser.add_argument("--symbol", required=True, help="Delta market symbol, e.g. ETHUSDT")
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=sorted(DELTA_RESOLUTIONS),
        help="Candle resolution",
    )
    parser.add_argument(
        "--start", required=True, type=parse_datetime, help="Range start (inclusive)"
    )
    parser.add_argument(
        "--end", required=True, type=parse_datetime, help="Range end (exclusive)"
    )
    parser.add_argument(
        "--max-candles-per-request",
        type=int,
        default=2000,
        help="Maximum candles per API request (documented Delta limit: 2000)",
    )
    return parser


async def main(argv: list[str] | None = None) -> int:
    """Run candle ingestion and return a process exit code."""
    setup_logging()
    args = build_parser().parse_args(argv)

    try:
        report: IngestReport = await ingest_candles(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start=args.start,
            end=args.end,
            max_candles_per_request=args.max_candles_per_request,
        )
    except Exception as exc:
        logger.exception("Candle ingestion failed: %s", exc)
        return 1

    logger.info(
        "Ingestion finished: symbol=%s timeframe=%s requests=%d received=%d "
        "accepted=%d rejected=%d inserted=%d duplicates_skipped=%d in %.2fs",
        report.symbol,
        report.timeframe,
        report.api_requests,
        report.received,
        report.accepted,
        report.rejected,
        report.inserted,
        report.duplicates_skipped,
        report.duration_seconds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
