"""Tests for `app.connectors.health.compute_health_status` — pure,
database-free classification, so every case is exercised directly against
fixed inputs rather than through a real ingestion run."""

from datetime import UTC, datetime, timedelta

from app.connectors.health import (
    FAILING_STREAK,
    STALE_MULTIPLIER,
    compute_health_status,
    entered_failing,
)

NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)
ONE_DAY = 86_400


class TestNeverIngested:
    def test_no_stored_point_at_all_is_never_ingested(self) -> None:
        assert (
            compute_health_status(latest_timestamp=None, expected_interval_seconds=ONE_DAY, now=NOW)
            == "never_ingested"
        )


class TestHealthy:
    def test_a_point_within_the_expected_interval_is_healthy(self) -> None:
        latest = NOW - timedelta(hours=1)
        assert (
            compute_health_status(
                latest_timestamp=latest, expected_interval_seconds=ONE_DAY, now=NOW
            )
            == "healthy"
        )

    def test_a_point_exactly_at_the_stale_threshold_is_still_healthy(self) -> None:
        """The threshold is a strict `>`, not `>=` — a connector at exactly
        `STALE_MULTIPLIER` intervals late has not yet crossed the line."""
        latest = NOW - timedelta(seconds=ONE_DAY * STALE_MULTIPLIER)
        assert (
            compute_health_status(
                latest_timestamp=latest, expected_interval_seconds=ONE_DAY, now=NOW
            )
            == "healthy"
        )

    def test_a_future_timestamp_is_healthy_not_a_crash(self) -> None:
        """Clock skew is not this function's problem to diagnose — a point
        somehow ahead of `now` is certainly not stale."""
        latest = NOW + timedelta(hours=1)
        assert (
            compute_health_status(
                latest_timestamp=latest, expected_interval_seconds=ONE_DAY, now=NOW
            )
            == "healthy"
        )


class TestStale:
    def test_a_point_past_the_stale_threshold_is_stale(self) -> None:
        latest = NOW - timedelta(seconds=ONE_DAY * STALE_MULTIPLIER + 1)
        assert (
            compute_health_status(
                latest_timestamp=latest, expected_interval_seconds=ONE_DAY, now=NOW
            )
            == "stale"
        )

    def test_scales_per_connector_not_one_flat_threshold(self) -> None:
        """The exact motivating example: a daily connector going 4 days
        with no new record is stale; a monthly connector (FRED's own real
        cadence) going 4 days is completely normal — the same absolute gap
        means something different for each connector's own cadence."""
        four_days_ago = NOW - timedelta(days=4)

        assert (
            compute_health_status(
                latest_timestamp=four_days_ago, expected_interval_seconds=ONE_DAY, now=NOW
            )
            == "stale"
        )
        assert (
            compute_health_status(
                latest_timestamp=four_days_ago,
                expected_interval_seconds=30 * ONE_DAY,
                now=NOW,
            )
            == "healthy"
        )


class TestNaiveTimestampNormalization:
    def test_a_naive_latest_timestamp_is_treated_as_utc(self) -> None:
        """SQLite round-trips a tz-aware DateTime column as naive (see
        `app.repositories.external_data._as_utc`'s own docstring) — this
        function must not silently misjudge every SQLite-backed row."""
        naive_latest = (NOW - timedelta(hours=1)).replace(tzinfo=None)
        assert (
            compute_health_status(
                latest_timestamp=naive_latest, expected_interval_seconds=ONE_DAY, now=NOW
            )
            == "healthy"
        )


class TestDefaultsToRealNow:
    def test_omitting_now_uses_the_real_current_time(self) -> None:
        """A point from years ago, with no `now` override, is stale
        against real wall-clock time — proves the default path works, not
        only the deterministic `now=` override every other test uses."""
        long_ago = datetime(2020, 1, 1, tzinfo=UTC)
        assert (
            compute_health_status(latest_timestamp=long_ago, expected_interval_seconds=ONE_DAY)
            == "stale"
        )


FRESH = NOW - timedelta(hours=1)
ALL_FAILED = [False] * FAILING_STREAK


class TestFailing:
    """A connector erroring on every tick must not read green just because
    its last good point is still recent — the deeper version of the same
    'looks healthy while doing nothing useful' failure this feature exists
    to catch."""

    def test_a_streak_of_failed_attempts_is_failing_even_with_fresh_data(self) -> None:
        assert (
            compute_health_status(
                latest_timestamp=FRESH,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=ALL_FAILED,
            )
            == "failing"
        )

    def test_failing_takes_precedence_over_stale(self) -> None:
        long_ago = NOW - timedelta(days=30)
        assert (
            compute_health_status(
                latest_timestamp=long_ago,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=ALL_FAILED,
            )
            == "failing"
        )

    def test_failing_takes_precedence_over_never_ingested(self) -> None:
        assert (
            compute_health_status(
                latest_timestamp=None,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=ALL_FAILED,
            )
            == "failing"
        )

    def test_fewer_attempts_than_the_streak_is_not_failing(self) -> None:
        """One or two failures is routinely a transient blip, not a verdict."""
        assert (
            compute_health_status(
                latest_timestamp=FRESH,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=[False] * (FAILING_STREAK - 1),
            )
            == "healthy"
        )

    def test_a_success_inside_the_streak_window_is_not_failing(self) -> None:
        mixed = [False] * (FAILING_STREAK - 1) + [True]
        assert (
            compute_health_status(
                latest_timestamp=FRESH,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=mixed,
            )
            == "healthy"
        )

    def test_only_the_newest_attempts_count_older_failures_do_not(self) -> None:
        """Newest first: a recent success followed by a long history of
        failures means the connector recovered."""
        recovered = [True] + [False] * 10
        assert (
            compute_health_status(
                latest_timestamp=FRESH,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=recovered,
            )
            == "healthy"
        )

    def test_a_longer_history_of_failures_is_still_failing(self) -> None:
        assert (
            compute_health_status(
                latest_timestamp=FRESH,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=[False] * 10,
            )
            == "failing"
        )

    def test_no_recorded_attempts_falls_back_to_staleness_alone(self) -> None:
        assert (
            compute_health_status(
                latest_timestamp=FRESH, expected_interval_seconds=ONE_DAY, now=NOW
            )
            == "healthy"
        )


class TestStaleAfterOverride:
    def test_the_override_replaces_the_default_multiple(self) -> None:
        latest = NOW - timedelta(days=45)
        # Default 3 x 30d = 90d threshold: still healthy at 45 days.
        assert (
            compute_health_status(
                latest_timestamp=latest, expected_interval_seconds=30 * ONE_DAY, now=NOW
            )
            == "healthy"
        )
        # A 40-day override flags the same point.
        assert (
            compute_health_status(
                latest_timestamp=latest,
                expected_interval_seconds=30 * ONE_DAY,
                now=NOW,
                stale_after_seconds=40 * ONE_DAY,
            )
            == "stale"
        )


class TestFredThresholds:
    """Pins the decision made from the real data: FRED is 60 days, judged
    against a 42-day real max gap, not the default 3 x 30 = 90."""

    def _fred(self):
        from app.connectors import load_builtin_connectors
        from app.connectors.fred import FRED_SOURCE
        from app.connectors.registry import default_registry

        load_builtin_connectors()
        return default_registry.describe(FRED_SOURCE)

    def test_fred_declares_a_60_day_stale_threshold_over_its_real_30_day_cadence(self) -> None:
        metadata = self._fred()
        assert metadata.expected_interval_seconds == 30 * ONE_DAY
        assert metadata.stale_after_seconds == 60 * ONE_DAY

    def test_the_real_max_observed_gap_of_42_days_is_not_flagged(self) -> None:
        metadata = self._fred()
        latest = NOW - timedelta(days=42)
        assert (
            compute_health_status(
                latest_timestamp=latest,
                expected_interval_seconds=metadata.expected_interval_seconds,
                stale_after_seconds=metadata.stale_after_seconds,
                now=NOW,
            )
            == "healthy"
        )

    def test_a_two_month_gap_is_stale(self) -> None:
        metadata = self._fred()
        latest = NOW - timedelta(days=61)
        assert (
            compute_health_status(
                latest_timestamp=latest,
                expected_interval_seconds=metadata.expected_interval_seconds,
                stale_after_seconds=metadata.stale_after_seconds,
                now=NOW,
            )
            == "stale"
        )


class TestEnteredFailing:
    """The transition, not the state: an alert built on this must fire once
    per outage, not once per tick. Sequences are newest first and include
    the attempt just recorded."""

    def test_the_attempt_that_completes_the_streak_is_the_transition(self) -> None:
        assert entered_failing([False, False, False]) is True

    def test_earlier_attempts_in_the_streak_are_not(self) -> None:
        assert entered_failing([False]) is False
        assert entered_failing([False, False]) is False

    def test_continuing_failures_after_the_transition_are_not(self) -> None:
        assert entered_failing([False, False, False, False]) is False
        assert entered_failing([False] * 10) is False

    def test_the_streak_completing_right_after_a_success_is_a_transition(self) -> None:
        assert entered_failing([False, False, False, True]) is True

    def test_a_streak_broken_by_a_success_is_not(self) -> None:
        assert entered_failing([False, False, True]) is False
        assert entered_failing([True, False, False, False]) is False

    def test_a_second_outage_after_recovery_is_a_new_transition(self) -> None:
        recovered_then_failed_again = [False, False, False, True, False, False, False]
        assert entered_failing(recovered_then_failed_again) is True

    def test_no_history_is_not_a_transition(self) -> None:
        assert entered_failing([]) is False

    def test_agrees_with_compute_health_status_on_when_failing_starts(self) -> None:
        """One definition of 'failing': the transition is exactly the moment
        the status flips to failing."""
        history: list[bool] = []
        flips = []
        for outcome in [True, False, False, False, False, True, False, False, False]:
            history.insert(0, outcome)
            was = compute_health_status(
                latest_timestamp=FRESH,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=history[1:],
            )
            now_status = compute_health_status(
                latest_timestamp=FRESH,
                expected_interval_seconds=ONE_DAY,
                now=NOW,
                recent_run_successes=history,
            )
            flips.append(entered_failing(history))
            assert entered_failing(history) == (now_status == "failing" and was != "failing")
        assert flips.count(True) == 2
