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
    "describe_health",
    "entered_failing",
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


def _streak_failed(recent_run_successes: Sequence[bool]) -> bool:
    latest_attempts = recent_run_successes[:FAILING_STREAK]
    return len(latest_attempts) == FAILING_STREAK and not any(latest_attempts)


def entered_failing(recent_run_successes: Sequence[bool]) -> bool:
    """Whether the newest attempt is the one that *made* the connector fail.

    `recent_run_successes` is newest first and includes the attempt just
    recorded. True only at the transition: the newest `FAILING_STREAK`
    attempts all failed, but the streak was not already complete one
    attempt earlier. Attempt number 4, 5, 6... of a continuing outage is
    not a transition, so an alert built on this fires once per outage, not
    once per tick.
    """
    return _streak_failed(recent_run_successes) and not _streak_failed(recent_run_successes[1:])


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
    if _streak_failed(recent_run_successes):
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


def describe_health(
    status: ConnectorHealthStatus,
    *,
    now: datetime | None = None,
    last_attempt_at: datetime | None = None,
    last_attempt_success: bool | None = None,
    next_sync_at: datetime | None = None,
    last_attempt_error: str | None = None,
) -> str | None:
    """A plain-English reason for a non-`healthy` status, or `None` for
    `healthy` (a fresh connector needs no explanation).

    Motivated directly by a real, live gap: a `stale` pill alone does not
    say whether the owning scheduler process has simply stopped ticking
    (an operational problem — the exact one found on 2026-09-27, where a
    local dev session had never started the standalone `scheduler_main`
    process introduced by the API/scheduler split, so every source it
    drives went quiet at the same time) or whether the scheduler is
    ticking normally and the upstream source itself has genuinely
    published nothing new (a real, non-actionable data condition — the
    same day, Marketaux's own live API confirmed zero new ETHUSD articles
    in four real days, `success=true` on every attempt). Both looked
    identical as a bare "Stale" badge; `next_sync_at` relative to `now`
    is what tells them apart, since a scheduler that stopped ticking never
    advances its own projected next attempt past "now," while one that is
    still running keeps pushing it into the future tick after tick.

    `failing` always surfaces the most recent attempt's own
    `last_attempt_error`, when the caller has one — the same message
    `ConnectorSyncRun.error_message` already stores per attempt but which
    reaching this function's caller depends on threading it through
    (`ConnectorDTO.last_attempt_error`), otherwise a real error sits in
    the database with no path to the person looking at the card.
    """
    if status == "healthy":
        return None

    current = now if now is not None else datetime.now(UTC)

    if status == "never_ingested":
        if last_attempt_at is None:
            return "No sync has been attempted for this source yet."
        if last_attempt_success is False:
            suffix = f": {last_attempt_error}" if last_attempt_error else "."
            return f"No data has been ingested yet — the last sync attempt failed{suffix}"
        return (
            "No data has been ingested yet, though the last sync attempt succeeded — "
            "the source may not have published anything in its backfill window yet."
        )

    if status == "failing":
        suffix = f": {last_attempt_error}" if last_attempt_error else "."
        return f"The last {FAILING_STREAK} sync attempts all failed{suffix}"

    # status == "stale"
    if next_sync_at is None:
        return (
            "No sync has been attempted since this value was stored — the scheduler "
            "process that owns this source may not be running."
        )
    if next_sync_at.tzinfo is None:
        next_sync_at = next_sync_at.replace(tzinfo=UTC)
    if next_sync_at <= current:
        return (
            "The next sync is overdue — the scheduler process that owns this source "
            "may not be running."
        )
    if last_attempt_success is False:
        suffix = f": {last_attempt_error}" if last_attempt_error else "."
        return f"The most recent sync attempt failed{suffix}"
    return (
        "The sync is running on schedule, but no new value has been published "
        "upstream recently — this source may genuinely have nothing new to report "
        "right now."
    )
