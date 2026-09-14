"""Login-specific lockout (M5-E2-T1, Redis-backed since M5-E3-T1) — a
dedicated brute-force / credential-stuffing defense on `POST
/auth/login`, deliberately separate from `app.middleware.rate_limit`'s
general fair-use throttling.

Closes a real, previously-disclosed gap: eight consecutive wrong-password
attempts against a real account each returned a plain `401` with no
throttling at all, confirmed live during M5-E1-T1's own verification
(`ARCHITECTURE.md` § "Authentication & Audit Trail"). Unlimited-attempt
brute-forcing of any known email was possible until this task.

Two backends behind one `LoginLockout` interface, exactly mirroring
`app.middleware.rate_limit`'s own Redis-vs-in-process split (see that
module's docstring, and `ARCHITECTURE.md` § "Redis", for the full
reasoning):

- `LoginLockoutTracker` — in-process, the original M5-E2-T1
  implementation and the fallback when `REDIS_URL` is unset.
- `RedisLoginLockoutTracker` — the same attempt-counting/window/cooldown
  algorithm, evaluated atomically in Redis via a single Lua script, with
  Redis's own key expiry replacing the manual prune entirely.

Both live on `app.state`, created fresh per `create_app()` call rather
than as a module-level singleton — a module-level tracker would leak
lockout state across the many independent `FastAPI` apps this test
suite creates.

Keyed by the raw *submitted* email, normalized but never resolved to a
real user id, and separately by client IP — either key alone can
trigger a lockout, so an unknown email locks out identically to a real
one after the same number of failures, preserving
`InvalidCredentialsError`'s own "never reveal which thing was wrong"
property. A successful login clears both keys immediately.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class LoginLockout(Protocol):
    async def seconds_locked(self, key: str) -> float: ...

    async def record_failure(self, key: str) -> bool: ...

    async def record_success(self, key: str) -> None: ...


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

    async def seconds_locked(self, key: str) -> float:
        """`> 0` while `key` is locked out; `0.0` when it may attempt again.

        A read-only check — never mutates state, so checking a key that
        was never recorded is always `0.0`. `async` purely to match
        `RedisLoginLockoutTracker`'s own interface — nothing here ever
        actually awaits.
        """
        record = self._records.get(key)
        if record is None:
            return 0.0
        remaining = record.locked_until - self._clock()
        return remaining if remaining > 0 else 0.0

    async def record_failure(self, key: str) -> bool:
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

    async def record_success(self, key: str) -> None:
        """Clear any tracked failures for `key` — a correct password
        (after, say, an earlier typo) is not held against the account
        once it succeeds."""
        self._records.pop(key, None)

    def _maybe_prune(self, now: float) -> None:
        """Drop records that are no longer locked and whose window has
        long since expired, once tracked keys pass a coarse bound.

        Without this, every distinct email or IP that ever failed even
        once stays resident for the life of the process — an unbounded
        dict growing forever. Cheap and approximate on purpose: this is
        a single-instance, in-process tracker, not a precision cache.
        (The Redis-backed tracker needs no equivalent — its keys expire
        on their own.)
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


#: Atomic attempt-count-and-lockout check. KEYS[1] is the lockout's own
#: Redis key (a hash: failures, window_started_at, locked_until); ARGV
#: is max_attempts, window_seconds, cooldown_seconds, now, and the TTL
#: to set (covering both the window and the cooldown, so an entry never
#: expires mid-lockout). Returns {just_locked (0/1), locked_until
#: (string)}.
_LOCKOUT_SCRIPT = """
local max_attempts = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cooldown = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local data = redis.call("HMGET", KEYS[1], "failures", "window_started_at", "locked_until")
local failures = tonumber(data[1])
local window_started_at = tonumber(data[2])
local locked_until = tonumber(data[3])
if locked_until == nil then locked_until = 0 end

if locked_until > now then
  return {0, tostring(locked_until)}
end

if failures == nil or window_started_at == nil or (now - window_started_at) > window then
  failures = 0
  window_started_at = now
end

failures = failures + 1
local just_locked = 0
if failures >= max_attempts then
  locked_until = now + cooldown
  just_locked = 1
end

redis.call("HSET", KEYS[1], "failures", failures, "window_started_at", window_started_at,
  "locked_until", locked_until)
redis.call("EXPIRE", KEYS[1], ttl)

return {just_locked, tostring(locked_until)}
"""


class RedisLoginLockoutTracker:
    """The same attempt-counting/window/cooldown algorithm as
    `LoginLockoutTracker`, evaluated atomically in Redis via
    `_LOCKOUT_SCRIPT` — a single `EVAL` round trip does the read,
    window-check, increment, and lockout decision, so concurrent
    requests for the same key can't race past the attempt limit the way
    two separate read-then-write calls could.

    **On a Redis error, every method delegates to an internal
    `LoginLockoutTracker` fallback instance — never a bare "treat as not
    locked".** Unlike the residual gap `RedisTokenBlocklist` still has to
    fail closed for, this fallback is a *complete*, independently
    correct enforcement mechanism (the exact same algorithm, just
    scoped to this process rather than durable across restarts) — so an
    attacker who causes or benefits from a Redis outage still faces a
    real attempt limit throughout it, never an unlimited-attempts
    window. The trade-off actually paid during an outage is durability
    (this process's own counters, not Redis's), not the protection
    itself. See `ARCHITECTURE.md` § "Redis" → "Mid-runtime failure
    handling" for the full reasoning, including why token revocation
    needed a different answer.
    """

    def __init__(
        self,
        client: redis.Redis,
        *,
        max_attempts: int,
        window_seconds: float,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._script = client.register_script(_LOCKOUT_SCRIPT)
        self._ttl = int(window_seconds + cooldown_seconds) + 1
        self._fallback = LoginLockoutTracker(
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            cooldown_seconds=cooldown_seconds,
        )

    async def seconds_locked(self, key: str) -> float:
        try:
            locked_until_raw = await self._client.hget(f"lockout:{key}", "locked_until")
        except Exception:
            logger.warning(
                "Redis unreachable checking lockout for %s; using in-process fallback "
                "(a real limit still applies, just not the durable Redis-backed one)",
                key,
            )
            return await self._fallback.seconds_locked(key)
        if locked_until_raw is None:
            return 0.0
        remaining = float(locked_until_raw) - self._clock()
        return remaining if remaining > 0 else 0.0

    async def record_failure(self, key: str) -> bool:
        try:
            just_locked, _locked_until = await self._script(
                keys=[f"lockout:{key}"],
                args=[
                    self._max_attempts,
                    self._window_seconds,
                    self._cooldown_seconds,
                    self._clock(),
                    self._ttl,
                ],
            )
        except Exception:
            logger.warning(
                "Redis unreachable recording login failure for %s; using in-process "
                "fallback (a real limit still applies, just not the durable one)",
                key,
            )
            return await self._fallback.record_failure(key)
        return bool(int(just_locked))

    async def record_success(self, key: str) -> None:
        try:
            await self._client.delete(f"lockout:{key}")
        except Exception:
            logger.warning("Redis unreachable clearing lockout for %s", key)
        # Cleared unconditionally, not just on the exception path above —
        # a success that reached Redis fine must still clear any record
        # the fallback accumulated during an *earlier* outage for this
        # same key, so a later Redis outage doesn't resurrect a stale
        # in-process lockout the user already logged in past.
        await self._fallback.record_success(key)


def build_login_lockout_tracker(
    client: redis.Redis | None,
    *,
    max_attempts: int,
    window_seconds: float,
    cooldown_seconds: float,
) -> LoginLockout:
    """`RedisLoginLockoutTracker` when `client` is available (a
    configured, reachable-at-startup Redis — see `app.core.redis`), else
    the in-process fallback."""
    if client is not None:
        return RedisLoginLockoutTracker(
            client,
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            cooldown_seconds=cooldown_seconds,
        )
    return LoginLockoutTracker(
        max_attempts=max_attempts,
        window_seconds=window_seconds,
        cooldown_seconds=cooldown_seconds,
    )
