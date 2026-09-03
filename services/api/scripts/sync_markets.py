"""Command-line entry point for Delta market synchronization.

Usage:
    uv run python scripts/sync_markets.py
"""

import asyncio
import logging
import sys

from app.core.logging import setup_logging
from app.services.market_sync import SyncReport, sync_markets

logger = logging.getLogger("scripts.sync_markets")


async def main() -> int:
    """Run the market sync and return a process exit code."""
    setup_logging()
    try:
        report: SyncReport = await sync_markets()
    except Exception as exc:
        logger.exception("Market sync failed: %s", exc)
        return 1
    logger.info(
        "Sync finished: fetched=%d inserted=%d updated=%d skipped=%d in %.2fs",
        report.products_fetched,
        report.inserted,
        report.updated,
        report.skipped,
        report.duration_seconds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
