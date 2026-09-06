"""Command-line entry point for a manual Ethereum gas price poll.

Matches `scripts/backfill_fear_greed.py`/`backfill_fred.py`'s own shape,
applied to the Etherscan connector — with one real difference worth
stating plainly rather than glossing over: **this is not a historical
backfill**. Gas Oracle has no historical query capability at all (see
`app/connectors/etherscan.py`'s own module docstring); running this
script performs exactly one live poll, timestamped at the moment it
runs, and stores that single point. `--start`/`--end` are accepted only
for symmetry with the other two backfill scripts and to let a caller
narrow the window a fetched point must fall within — they cannot make
this script produce more than one point, or reach further into the past
than "right now".

Usage:
    uv run python scripts/backfill_etherscan.py
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from app.connectors.etherscan import ETHERSCAN_SOURCE
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.external_data_ingest import run_ingest_once


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Poll the current Ethereum gas price into external_data_points. Not a "
            "historical backfill — Gas Oracle has no history to backfill; see this "
            "script's own module docstring."
        ),
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
    report = await run_ingest_once(source=ETHERSCAN_SOURCE, start=resolved_start, end=resolved_end)
    print(
        f"source={report.source} received={report.received} inserted={report.inserted} "
        f"updated={report.updated} duplicates_skipped={report.duplicates_skipped} "
        f"rejected={report.rejected} "
        f"duration={report.duration_seconds:.2f}s"
    )
    return 0 if report.rejected == 0 else 1


def main() -> None:
    """Parse arguments and run one poll."""
    args = build_parser().parse_args()
    sys.exit(asyncio.run(_main(args.start, args.end)))


if __name__ == "__main__":
    main()
