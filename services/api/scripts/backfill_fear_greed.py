"""Command-line entry point for a manual Fear & Greed Index backfill.

Fetches every recorded value in the requested range using the same
idempotent ingestion path the periodic scheduler uses — matches
`scripts/sync_candles.py`'s own shape, applied to one connector source
instead of a symbol/timeframe pair.

Usage:
    uv run python scripts/backfill_fear_greed.py
    uv run python scripts/backfill_fear_greed.py --start 2018-02-01 --end 2026-01-01
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from app.connectors.fear_greed import FEAR_GREED_SOURCE
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.external_data_ingest import run_ingest_once


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Backfill the Fear & Greed Index into external_data_points.",
    )
    parser.add_argument(
        "--start",
        help="Range start, YYYY-MM-DD (defaults to external_data_sync_backfill_days ago)",
    )
    parser.add_argument(
        "--end",
        help="Range end, YYYY-MM-DD (defaults to now)",
    )
    return parser


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


async def _main(start: str | None, end: str | None) -> int:
    setup_logging()
    settings = get_settings()
    resolved_end = _parse_date(end) or datetime.now(UTC)
    resolved_start = _parse_date(start) or (
        resolved_end - timedelta(days=settings.external_data_sync_backfill_days)
    )
    report = await run_ingest_once(source=FEAR_GREED_SOURCE, start=resolved_start, end=resolved_end)
    print(
        f"source={report.source} received={report.received} inserted={report.inserted} "
        f"duplicates_skipped={report.duplicates_skipped} rejected={report.rejected} "
        f"duration={report.duration_seconds:.2f}s"
    )
    return 0 if report.rejected == 0 else 1


def main() -> None:
    """Parse arguments and run one backfill pass."""
    args = build_parser().parse_args()
    sys.exit(asyncio.run(_main(args.start, args.end)))


if __name__ == "__main__":
    main()
