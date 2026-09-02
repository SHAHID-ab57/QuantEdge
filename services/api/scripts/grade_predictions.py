"""Command-line entry point for one prediction grading pass.

Grades every persisted prediction whose target horizon has arrived using
the same logic as the periodic scheduler. Useful for operations and manual
verification.

Usage:
    uv run python scripts/grade_predictions.py
"""

import asyncio
import sys

from app.core.logging import setup_logging
from app.services.grading_scheduler import run_grading_once


async def _main() -> int:
    setup_logging()
    summary = await run_grading_once()
    print(
        f"attempted={summary.attempted} graded={summary.graded} "
        f"not_yet_knowable={summary.not_yet_knowable} failed={summary.failed} "
        f"duration={summary.duration_seconds:.2f}s"
    )
    return 0 if summary.failed == 0 else 1


def main() -> None:
    """Run one grading pass."""
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
