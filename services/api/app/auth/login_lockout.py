"""Login-specific lockout (M5-E2-T1) — a dedicated brute-force /
credential-stuffing defense on `POST /auth/login`, deliberately separate
from `app.middleware.rate_limit`'s general fair-use throttling.

Closes a real, previously-disclosed gap: eight consecutive wrong-password
attempts against a real account each returned a plain `401` with no
throttling at all, confirmed live during M5-E1-T1's own verification
(`ARCHITECTURE.md` § "Authentication & Audit Trail"). Unlimited-attempt
brute-forcing of any known email was possible until this task.

Tracked in-process, on `app.state` (never a module-level singleton — see
`app.middleware.rate_limit`'s own docstring for why that would leak
state across the many independent `FastAPI` apps this test suite
creates). Keyed by the raw *submitted* email, normalized but never
resolved to a real user id, and separately by client IP — either key
alone can trigger a lockout, so an unknown email locks out identically
to a real one after the same number of failures, preserving
`InvalidCredentialsError`'s own "never reveal which thing was wrong"
property. A successful login clears both keys immediately.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Record:
    failures: int
    window_started_at: float
    locked_until: float = 0.0


class LoginLockoutTracker:
    """`max_attempts` consecutive failures for one key within
    `window_seconds` locks that key out for `cooldown_seconds`.

    `clock` is injectable so tests can control time exactly rather than
    sleeping in real time.
    """

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: float,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._records: dict[str, _Record] = {}

    def seconds_locked(self, key: str) -> float:
        """`> 0` while `key` is locked out; `0.0` when it may attempt again.

        A read-only check — never mutates state, so checking a key that
        was never recorded is always `0.0`.
        """
        record = self._records.get(key)
        if record is None:
            return 0.0
        remaining = record.locked_until - self._clock()
        return remaining if remaining > 0 else 0.0

    def record_failure(self, key: str) -> bool:
        """Count one more failed attempt for `key`.

        A failure outside the rolling `window_seconds` starts a fresh
        window rather than accumulating forever — this is a burst
        detector, not a lifetime ban counter. A no-op (returns `False`)
        while `key` is already locked out: the caller is expected to
        check `seconds_locked` first and never reach `AuthService.login`
        (and so never call this) during an active lockout, but staying a
        no-op here too means a stray call can't reset `window_started_at`
        and accidentally clear a still-active `locked_until` early.

        Returns `True` exactly on the call that crosses `max_attempts` —
        the moment `key` transitions into a lockout, not every failure
        — so the caller can log that transition once, not on every
        subsequent rejected attempt.
        """
        now = self._clock()
        record = self._records.get(key)
        if record is not None and now < record.locked_until:
            return False
        if record is None or now - record.window_started_at > self._window_seconds:
            record = _Record(failures=0, window_started_at=now)
            self._records[key] = record
        record.failures += 1
        just_locked = False
        if record.failures >= self._max_attempts:
            record.locked_until = now + self._cooldown_seconds
            just_locked = True
        self._maybe_prune(now)
        return just_locked

    def record_success(self, key: str) -> None:
        """Clear any tracked failures for `key` — a correct password
        (after, say, an earlier typo) is not held against the account
        once it succeeds."""
        self._records.pop(key, None)

    def _maybe_prune(self, now: float) -> None:
        """Drop records that are no longer locked and whose window has
        long since expired, once tracked keys pass a coarse bound.

        Without this, every distinct email or IP that ever failed even
        once stays resident for the life of the process — an unbounded
        dict growing forever, unlike `app.middleware.rate_limit
        .TokenBucketRateLimiter`'s own bounded prune, which this mirrors.
        Cheap and approximate on purpose (see that class's own docstring
        on why): this is a single-instance, in-process tracker, not a
        precision cache.
        """
        if len(self._records) <= 10_000:
            return
        stale = [
            key
            for key, record in self._records.items()
            if now >= record.locked_until and now - record.window_started_at > self._window_seconds
        ]
        for key in stale:
            del self._records[key]
