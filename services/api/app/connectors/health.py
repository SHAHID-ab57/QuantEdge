"""Connector health status — a signal, not alerting.

Three real, previously-silent bugs motivated this (`ARCHITECTURE.md` §
"Connector Health Monitoring" has the full account): Fear & Greed's
missing `external_sources` field, FRED's silent date-defaulting that
discarded 865 of 866 real values, and Etherscan's clock-read timing bug
that would have produced zero new rows on every tick forever. All three
looked perfectly healthy from the outside — no error raised, no crash, no
alert — because nothing on this platform ever asked "how long has it been
since this connector's data actually moved forward?" This module answers
that question, plus its deeper sibling: is the sync itself failing? (a
connector erroring on every tick can still have a recent-enough last good
point, so staleness alone would keep showing it green). Computing a health
status is pure, synchronous, and database-free (`compute_health_status`
takes already-queried data, not a session) — wiring the result into an
actual notification is a deliberately separate, later piece of this epic.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

__all__ = [
    "FAILING_STREAK",
    "STALE_MULTIPLIER",
    "ConnectorHealthStatus",
    "compute_health_status",
]

ConnectorHealthStatus = Literal["healthy", "stale", "failing", "never_ingested"]

#: How many multiples of a connector's own `expected_interval_seconds` may
#: pass with no new stored point before it's flagged stale. Matches this
#: feature's own motivating example exactly: a daily connector going one
#: day with no new record is normal, going three or more is not.
STALE_MULTIPLIER = 3

#: How many of a connector's most recent sync attempts must *all* have
#: failed before it is reported `failing`. Three, not one: a single failed
#: tick is routinely a transient network blip or upstream 5xx, and flagging
#: every one would teach people to ignore the signal, the same reason
#: `news_sentiment`'s cadence was corrected for weekends. Three consecutive
#: failures is three hours of continuous failure for an hourly-ticking
#: connector, and eighteen for Marketaux's 6h scheduler: long enough to be
#: real, short enough that it does not wait out a staleness threshold
#: (up to 60 days for FRED) to be noticed.
FAILING_STREAK = 3


def compute_health_status(
    *,
    latest_timestamp: datetime | None,
    expected_interval_seconds: int,
    now: datetime | None = None,
    stale_after_seconds: int | None = None,
    recent_run_successes: Sequence[bool] = (),
) -> ConnectorHealthStatus:
    """Classify one connector's health.

    `failing` — the connector's `FAILING_STREAK` most recent sync attempts
    all failed. Checked first and takes precedence over everything else:
    a connector erroring on every tick while its last good point is still
    inside the staleness window is a different, more urgent situation than
    plain staleness (its data has not stopped moving yet, but nothing is
    about to move it), and it is the root cause when the two coincide.
    `recent_run_successes` is newest first, one bool per attempt; fewer
    than `FAILING_STREAK` attempts on record is never `failing`.

    `never_ingested` — no point has ever been stored for this source.
    `stale` — the newest point is older than this connector's staleness
    threshold: `stale_after_seconds` when the connector sets one, else
    `STALE_MULTIPLIER` times its own `expected_interval_seconds`
    (`ConnectorMetadata`'s own fields, scaled per connector rather than
    one flat threshold — see them for why each value is what it is).
    `healthy` — everything else, including a `latest_timestamp` that is
    somehow in the future (a clock skew is not this function's problem to
    diagnose; it is certainly not "stale").

    A failure streak is judged from recorded attempts alone, with no
    recency bound: if the scheduler itself later stops, the last known
    state stays `failing` until a success is recorded, and staleness is
    what eventually reports the silence.
    """
    latest_attempts = recent_run_successes[:FAILING_STREAK]
    if len(latest_attempts) == FAILING_STREAK and not any(latest_attempts):
        return "failing"
    if latest_timestamp is None:
        return "never_ingested"
    if latest_timestamp.tzinfo is None:
        latest_timestamp = latest_timestamp.replace(tzinfo=UTC)
    current = now if now is not None else datetime.now(UTC)
    age_seconds = (current - latest_timestamp).total_seconds()
    threshold = (
        stale_after_seconds
        if stale_after_seconds is not None
        else expected_interval_seconds * STALE_MULTIPLIER
    )
    if age_seconds > threshold:
        return "stale"
    return "healthy"
