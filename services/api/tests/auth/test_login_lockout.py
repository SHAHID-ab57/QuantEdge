"""Unit and end-to-end tests for the login-specific lockout (M5-E2-T1) —
`app.auth.login_lockout.LoginLockoutTracker` in isolation with a fake,
injectable clock, plus real repeated `POST /auth/login` calls proving the
whole thing actually locks a real account out through the real endpoint.

Directly closes the disclosed gap from M5-E1-T1's own live verification:
eight consecutive wrong-password attempts against a real account each
returned a plain `401` with no throttling at all. This file's own
`TestRealLockoutThroughTheEndpoint.test_the_exact_eight_attempt_sequence_from_the_last_tasks_verification_now_locks_out`
repeats that exact scenario and asserts it no longer succeeds unlimited times.
"""

import httpx
import pytest

from app.auth.login_lockout import LoginLockoutTracker
from app.models import User


class FakeClock:
    """Same pattern as `tests/unit/middleware/test_rate_limit.py`'s own
    `FakeClock` — an explicitly-advanced clock, never a real sleep."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestLoginLockoutTrackerUnit:
    def test_a_fresh_key_is_never_locked(self) -> None:
        tracker = LoginLockoutTracker(
            max_attempts=3, window_seconds=60, cooldown_seconds=300, clock=FakeClock()
        )
        assert tracker.seconds_locked("email:nobody@example.com") == 0.0

    def test_fewer_than_max_attempts_does_not_lock(self) -> None:
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=3, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        assert tracker.record_failure("email:x") is False
        assert tracker.record_failure("email:x") is False
        assert tracker.seconds_locked("email:x") == 0.0

    def test_the_max_attempt_th_failure_locks_and_returns_true_exactly_once(self) -> None:
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=3, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        assert tracker.record_failure("email:x") is False
        assert tracker.record_failure("email:x") is False
        assert tracker.record_failure("email:x") is True  # the transition into lockout
        assert tracker.seconds_locked("email:x") == pytest.approx(300.0)

    def test_further_failures_while_already_locked_are_a_silent_no_op(self) -> None:
        """A stray call during an active lockout (the endpoint is expected
        to check `seconds_locked` first and never reach this) must not
        reset the window and accidentally shorten the lockout."""
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=2, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        tracker.record_failure("email:x")
        tracker.record_failure("email:x")  # now locked
        clock.advance(250.0)  # still within the 300s cooldown
        assert tracker.record_failure("email:x") is False  # no-op, not a re-trigger
        assert tracker.seconds_locked("email:x") == pytest.approx(50.0)

    def test_the_cooldown_expiring_unlocks_the_key(self) -> None:
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=2, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        tracker.record_failure("email:x")
        tracker.record_failure("email:x")
        assert tracker.seconds_locked("email:x") > 0
        clock.advance(300.0)
        assert tracker.seconds_locked("email:x") == 0.0

    def test_a_failure_outside_the_window_does_not_accumulate_toward_a_lockout(self) -> None:
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=3, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        tracker.record_failure("email:x")
        clock.advance(61.0)  # outside the 60s window — the count resets
        tracker.record_failure("email:x")
        tracker.record_failure("email:x")
        # Only 2 failures inside the *current* window, one short of max_attempts.
        assert tracker.seconds_locked("email:x") == 0.0

    def test_success_clears_the_failure_count(self) -> None:
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=3, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        tracker.record_failure("email:x")
        tracker.record_failure("email:x")
        tracker.record_success("email:x")
        # Back to zero — two more failures alone must not lock it out.
        tracker.record_failure("email:x")
        tracker.record_failure("email:x")
        assert tracker.seconds_locked("email:x") == 0.0

    def test_two_different_keys_are_tracked_independently(self) -> None:
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=2, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        tracker.record_failure("email:a@example.com")
        tracker.record_failure("email:a@example.com")
        assert tracker.seconds_locked("email:a@example.com") > 0
        assert tracker.seconds_locked("email:b@example.com") == 0.0

    def test_stale_records_are_pruned_once_the_tracker_grows_large(self) -> None:
        """Without this, every distinct email/IP that ever failed once
        stays resident for the life of the process — an unbounded dict.
        Mirrors `TokenBucketRateLimiter`'s own bounded prune."""
        clock = FakeClock()
        tracker = LoginLockoutTracker(
            max_attempts=100, window_seconds=60, cooldown_seconds=300, clock=clock
        )
        for i in range(10_001):
            tracker.record_failure(f"email:stale-{i}@example.com")
        clock.advance(61.0)  # every one of those records' window has now expired
        # One more failure (a real, current key) is enough to trigger the
        # opportunistic prune inside `record_failure` itself.
        tracker.record_failure("email:current@example.com")
        assert len(tracker._records) < 10_001, (
            "stale records were never pruned — the tracker grows unbounded"
        )


@pytest.mark.asyncio
class TestRealLockoutThroughTheEndpoint:
    async def test_the_exact_eight_attempt_sequence_from_the_last_tasks_verification_now_locks_out(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        """M5-E1-T1's own live verification sent eight consecutive
        wrong-password requests against a real account and found every
        single one returned a plain `401` with no throttling. Repeating
        that exact scenario here must now produce at least one `429`."""
        statuses = []
        for i in range(8):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": registered_user.email, "password": f"wrong-guess-{i}"},
            )
            statuses.append(response.status_code)

        assert 429 in statuses, statuses
        # Once locked, the correct password must not succeed either —
        # exactly the "unlimited-attempt brute-forcing" gap this closes.
        still_locked = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        assert still_locked.status_code == 429
        assert still_locked.json()["code"] == "too_many_login_attempts"
        assert "Retry-After" in still_locked.headers

    async def test_an_unknown_email_locks_out_identically_to_a_real_one(
        self, client: httpx.AsyncClient
    ) -> None:
        """Preserves `InvalidCredentialsError`'s own enumeration-resistance:
        the lockout tracks the *submitted* email, never a resolved user
        id, so a fabricated email is throttled exactly the same way."""
        statuses = []
        for i in range(6):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "definitely-nobody@example.com", "password": f"guess-{i}"},
            )
            statuses.append(response.status_code)
        assert 429 in statuses, statuses

    async def test_a_successful_login_before_the_threshold_clears_the_failure_count(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        """A couple of typos followed by the correct password must not
        leave the account primed to lock out on the next unrelated typo —
        `record_success` clears the count immediately."""
        for i in range(2):
            await client.post(
                "/api/v1/auth/login",
                json={"email": registered_user.email, "password": f"typo-{i}"},
            )
        good = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        assert good.status_code == 200

        # Two more failures alone (well under the default max_attempts)
        # must not lock the account out post-reset.
        for i in range(2):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": registered_user.email, "password": f"typo-again-{i}"},
            )
            assert response.status_code == 401
