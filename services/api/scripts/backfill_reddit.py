"""Command-line entry point for a manual Reddit comment backfill.

Matches `scripts/backfill_marketaux.py`'s own shape, applied to
`app.services.reddit_ingest.ingest_reddit` instead — Reddit persists real
comments into its own `reddit_comments` table and mirrors two derived
daily aggregates, not a raw point straight into `external_data_points`
(see `app.connectors.reddit`'s own module docstring for the full design).

Unlike Marketaux's own free tier (100 requests/day, forcing a patient,
multi-run backfill), Arctic Shift has no documented daily request quota
— but its own README asks that bulk extraction stay off the live API in
favor of its monthly dumps. This script honors that spirit even without a
hard quota to budget against: it walks backward through history in
`--chunk-days`-sized windows (default 30), pausing `--pause-seconds`
between each (default 2), so a wide historical backfill still reads as
"a couple requests per second," never a burst.

A real run over 180 days confirmed Arctic Shift's informal rate limit
has a cumulative component, not just a per-request one: steady, paced
requests (already spaced by both `--pause-seconds` and the connector's
own `reddit_page_pause_seconds`) still tip into a sustained run of
HTTP 422s that the connector's own 5-attempt, exponential-backoff
retry (capped at 8s) cannot clear. This script treats that as an
expected, recoverable condition: on a chunk failure it sleeps
`--chunk-cooldown-seconds` and retries the same chunk, up to
`--chunk-max-retries` times, before giving up for good.

A first attempt at this used a 90s cooldown — real evidence from a
second full run showed that was still too short: three independent
throttle episodes all showed the same shape (a fresh ~14-16 request
allowance drained in under a minute, then sustained 422s), and a
90s rest was not enough to let the next attempt clear more than
another ~14-16 requests before throttling again. The default below
(5 minutes) reflects that observed recovery behavior, not a guess.

Usage:
    uv run python scripts/backfill_reddit.py
    uv run python scripts/backfill_reddit.py --start 2024-01-01 --end 2024-02-01
    uv run python scripts/backfill_reddit.py --days 365 --chunk-days 14
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from app.connectors.errors import ConnectorAPIError, ConnectorNetworkError
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.reddit_ingest import ingest_reddit


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Backfill Reddit comments (via Arctic Shift) into reddit_comments.",
    )
    parser.add_argument(
        "--start",
        help="Range start, YYYY-MM-DD (defaults to --days ago)",
    )
    parser.add_argument(
        "--end",
        help="Range end, YYYY-MM-DD (defaults to now)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Days of history to backfill when --start is omitted "
        "(defaults to reddit_sync_backfill_days)",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Days per ingest call — walked backward through the full range one chunk "
        "at a time (default 7, deliberately small: reddit_max_pages_per_fetch=20 "
        "pages/subreddit per call could otherwise silently truncate a wide chunk for "
        "a busy subreddit like CryptoCurrency at 100+ comments/day)",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=2.0,
        help="Delay between chunks, keeping this well inside Arctic Shift's own "
        "'a couple requests per second' fair-use guidance (default 2.0)",
    )
    parser.add_argument(
        "--chunk-cooldown-seconds",
        type=float,
        default=300.0,
        help="Sleep before retrying a chunk that failed with a real API/network "
        "error (default 300 — a 90s cooldown was tried first and confirmed too "
        "short by a real run: it only let ~14-16 more requests through before "
        "the next sustained throttle)",
    )
    parser.add_argument(
        "--chunk-max-retries",
        type=int,
        default=5,
        help="Retries per chunk after a cooldown before giving up entirely (default 5)",
    )
    return parser


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


async def _main(
    start: str | None,
    end: str | None,
    days: int | None,
    chunk_days: int,
    pause_seconds: float,
    chunk_cooldown_seconds: float,
    chunk_max_retries: int,
) -> int:
    setup_logging()
    settings = get_settings()
    resolved_end = _parse_date(end) or datetime.now(UTC)
    backfill_days = days if days is not None else settings.reddit_sync_backfill_days
    resolved_start = _parse_date(start) or (resolved_end - timedelta(days=backfill_days))
    if resolved_end < resolved_start:
        print("error: end must not be before start", file=sys.stderr)
        return 1

    total_received = total_inserted = total_duplicates = total_rejected = 0
    chunk_end = resolved_end
    first_chunk = True
    while chunk_end > resolved_start:
        chunk_start = max(resolved_start, chunk_end - timedelta(days=chunk_days))
        if not first_chunk:
            await asyncio.sleep(pause_seconds)
        first_chunk = False

        report = None
        for attempt in range(chunk_max_retries + 1):
            try:
                report = await ingest_reddit(start=chunk_start, end=chunk_end)
                break
            except (ConnectorAPIError, ConnectorNetworkError) as exc:
                if attempt == chunk_max_retries:
                    print(
                        f"error: chunk [{chunk_start.date()} .. {chunk_end.date()}] "
                        f"failed after {chunk_max_retries} cooldown retries: {exc}",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    f"warning: chunk [{chunk_start.date()} .. {chunk_end.date()}] failed "
                    f"({exc}); cooling down {chunk_cooldown_seconds:.0f}s before retry "
                    f"{attempt + 1}/{chunk_max_retries}",
                    file=sys.stderr,
                )
                await asyncio.sleep(chunk_cooldown_seconds)
        assert report is not None
        total_received += report.received
        total_inserted += report.inserted
        total_duplicates += report.duplicates_skipped
        total_rejected += report.rejected
        print(
            f"[{chunk_start.date()} .. {chunk_end.date()}] received={report.received} "
            f"inserted={report.inserted} duplicates_skipped={report.duplicates_skipped} "
            f"rejected={report.rejected} days_recomputed={report.days_recomputed} "
            f"duration={report.duration_seconds:.2f}s"
        )
        chunk_end = chunk_start

    print(
        f"TOTAL received={total_received} inserted={total_inserted} "
        f"duplicates_skipped={total_duplicates} rejected={total_rejected}"
    )
    return 0 if total_rejected == 0 else 1


def main() -> None:
    """Parse arguments and run the full backfill."""
    args = build_parser().parse_args()
    sys.exit(
        asyncio.run(
            _main(
                args.start,
                args.end,
                args.days,
                args.chunk_days,
                args.pause_seconds,
                args.chunk_cooldown_seconds,
                args.chunk_max_retries,
            )
        )
    )


if __name__ == "__main__":
    main()
