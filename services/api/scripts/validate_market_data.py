"""Command-line entry point for market data quality validation.

Read-only: validates the integrity of stored OHLCV candles (duplicates,
gaps, OHLC relationships, volume sign, bucket alignment, UTC timestamps,
ordering) and prints a quality report.

Usage:
    uv run python scripts/validate_market_data.py \
        --symbol ETHUSDT \
        --timeframe 1h

Optional range (dates may be ``YYYY-MM-DD`` or ISO datetimes; when omitted,
the observed span of stored candles is validated):
    uv run python scripts/validate_market_data.py \
        --symbol ETHUSDT \
        --timeframe 1h \
        --start 2026-01-01 \
        --end 2026-01-31
"""

import argparse
import asyncio
import logging
import sys

from app.core.logging import setup_logging
from app.models.candle import TIMEFRAMES
from app.services.candle_validation import (
    DEFAULT_ISSUE_LIMIT,
    CandleValidationError,
    ValidationReport,
    validate_candles,
)
from scripts.ingest_candles import parse_datetime

logger = logging.getLogger("scripts.validate_market_data")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate the quality of stored OHLCV market data.",
    )
    parser.add_argument("--symbol", required=True, help="Market symbol, e.g. ETHUSDT")
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=list(TIMEFRAMES),
        help="Candle resolution",
    )
    parser.add_argument(
        "--start",
        type=parse_datetime,
        default=None,
        help="Validation range start (inclusive); defaults to the observed span",
    )
    parser.add_argument(
        "--end",
        type=parse_datetime,
        default=None,
        help="Validation range end (exclusive); defaults to the observed span",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_ISSUE_LIMIT,
        help="Maximum issues/missing timestamps printed (counts stay exact)",
    )
    return parser


def _print_report(report: ValidationReport) -> None:
    """Print a human-readable quality report."""
    range_text = (
        f"[{report.start.isoformat()}, {report.end.isoformat()})"
        if report.start is not None and report.end is not None
        else "no candles stored"
    )
    print("Market data quality report")
    print("==========================")
    print(f"symbol:                {report.symbol}")
    print(f"timeframe:             {report.timeframe}")
    print(f"range:                 {range_text}")
    print(f"total candles:         {report.total_candles}")
    print(f"expected candles:      {report.expected_candles}")
    print(f"missing candles:       {report.missing_candles}")
    print(f"duplicate records:     {report.duplicate_count}")
    print(f"invalid candles:       {report.invalid_candles}")
    print(f"coverage:              {report.coverage_percent:.2f}%")
    print(f"validity:              {report.validity_percent:.2f}%")
    print(f"quality score:         {report.quality_score:.2f}%")
    print(f"validation duration:   {report.duration_seconds:.2f}s")

    if report.issues:
        print(f"\nIssues (first {len(report.issues)}):")
        for issue in report.issues:
            reasons = ", ".join(issue.reasons)
            print(f"  - {issue.open_time.isoformat()}: {reasons}")
    if report.missing_timestamps:
        print(f"\nMissing timestamps (first {len(report.missing_timestamps)}):")
        for missing in report.missing_timestamps:
            print(f"  - {missing.isoformat()}")


async def main(argv: list[str] | None = None) -> int:
    """Run market data validation and return a process exit code."""
    setup_logging()
    args = build_parser().parse_args(argv)

    try:
        report: ValidationReport = await validate_candles(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start=args.start,
            end=args.end,
            issue_limit=args.limit,
        )
    except (CandleValidationError, ValueError) as exc:
        logger.error("Validation failed: %s", exc)
        return 1
    except Exception as exc:
        logger.exception("Validation failed: %s", exc)
        return 1

    _print_report(report)
    logger.info(
        "Validation finished: symbol=%s timeframe=%s total=%d expected=%d "
        "missing=%d duplicates=%d invalid=%d quality=%.2f%% in %.2fs",
        report.symbol,
        report.timeframe,
        report.total_candles,
        report.expected_candles,
        report.missing_candles,
        report.duplicate_count,
        report.invalid_candles,
        report.quality_score,
        report.duration_seconds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
