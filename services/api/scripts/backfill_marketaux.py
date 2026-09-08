"""Command-line entry point for a manual Marketaux news backfill.

Matches `scripts/backfill_fear_greed.py`'s own shape, applied to
`app.services.news_ingest.ingest_news` instead of the generic
`external_data_ingest` path — News persists real articles into its own
`news_articles` table and mirrors a derived daily aggregate, not a raw
point straight into `external_data_points` (see `app.connectors.marketaux`'s
own module docstring for the full design).

The free tier's own real constraints (100 requests/day, 3 articles per
request — see that module's own docstring point 2) mean a genuinely wide
historical backfill needs patience: this script paginates up to
`marketaux_max_pages_per_fetch` pages per run, same as a periodic tick: run
it more than once, with progressively earlier `--start` values, to work
back through more history without exhausting a single day's request quota.

Usage:
    uv run python scripts/backfill_marketaux.py
    uv run python scripts/backfill_marketaux.py --start 2026-01-01 --end 2026-02-01
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.news_ingest import run_ingest_once


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Backfill Marketaux news articles into news_articles.",
    )
    parser.add_argument(
        "--start",
        help="Range start, YYYY-MM-DD (defaults to news_sync_backfill_days ago)",
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
        resolved_end - timedelta(days=settings.news_sync_backfill_days)
    )
    report = await run_ingest_once(start=resolved_start, end=resolved_end)
    print(
        f"received={report.received} inserted={report.inserted} "
        f"duplicates_skipped={report.duplicates_skipped} rejected={report.rejected} "
        f"days_recomputed={report.days_recomputed} duration={report.duration_seconds:.2f}s"
    )
    return 0 if report.rejected == 0 else 1


def main() -> None:
    """Parse arguments and run one backfill pass."""
    args = build_parser().parse_args()
    sys.exit(asyncio.run(_main(args.start, args.end)))


if __name__ == "__main__":
    main()
