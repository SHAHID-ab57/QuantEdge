"""Token revocation (M5-E3-T1) — closes the gap M5-E1-T1 disclosed and
deliberately deferred: logout never invalidated a token server-side, so
a captured token stayed fully valid and replayable for its full
remaining lifetime regardless of logout.

`POST /auth/logout` (`app.api.v1.endpoints.auth`) blocklists the calling
token's own `jti`, with a TTL matching its *own* remaining lifetime
(`claims.expires_at - now`) — a blocklist entry never outlives the token
it blocks, so this never accumulates entries for tokens that would have
expired naturally anyway. `get_current_user` checks the blocklist on
every authenticated request.

Two backends behind one interface, exactly mirroring `app.middleware
.rate_limit` and `app.auth.login_lockout`'s own Redis-vs-in-process
split — see `ARCHITECTURE.md` § "Redis" for the full reasoning:

- `InProcessTokenBlocklist` — a plain dict, the fallback when
  `REDIS_URL` is unset. Restart-resets, single-instance only, exactly
  the pre-existing characteristic this task's other two mechanisms
  already had before Redis was wired in.
- `RedisTokenBlocklist` — `SET`/`EXISTS` against Redis, TTL-expiring
  entries automatically (no manual pruning needed at all, unlike the
  in-process fallback, which does its own lazy sweep). **Fails
  *closed*, not open, on a Redis error** — unlike the other two
  mechanisms in this task. A revoked-then-silently-treated-as-valid
  token would quietly undo the one thing this feature exists to do, the
  first time a real Redis blip coincided with a real logout; that's a
  categorically different risk than a rate limiter or a lockout briefly
  running in degraded mode (see `ARCHITECTURE.md` § "Redis" → "Mid-
  runtime failure handling" for the full reasoning, including why the
  other two *don't* need this). Every `revoke()` writes through to an
  internal `InProcessTokenBlocklist` as well as Redis, so — since this
  platform runs a single instance today — every revocation this process
  has ever issued stays known to it even if Redis becomes unreachable
  immediately afterward; `is_revoked()` checks that local copy first
  (fast, and complete for anything revoked during this process's own
  lifetime) and only reaches Redis for the durable, cross-restart
  record. Only when *neither* source can answer — the local copy has no
  record *and* Redis errors — does it raise `RevocationCheckUnavailableError`
  (503), rather than guessing "not revoked". **In practice this means
  nearly every authenticated request during a Redis outage**, not just
  replays of already-revoked tokens: the local copy only ever shortcuts
  the check *positively* (a record there is trusted immediately), never
  negatively (no record is never treated as proof of anything, since a
  restart could have discarded it) — so a perfectly ordinary, never-
  revoked token still needs a real Redis round trip, and fails closed
  exactly like a genuinely-revoked one would if that round trip errors.
  Confirmed directly against a real, deliberately-unreachable Redis
  connection, not assumed — see `RevocationCheckUnavailableError`'s own
  docstring for the exact result.
"""

import logging
import time
from typing import Protocol

import redis.asyncio as redis

from app.auth.errors import RevocationCheckUnavailableError

logger = logging.getLogger(__name__)


class TokenBlocklist(Protocol):
    """Revoke one token by its `jti`, and check whether it's revoked.

    `is_revoked` may raise `RevocationCheckUnavailableError` — a
    revocation status that genuinely cannot be determined must never be
    silently reported as `False` (see `RedisTokenBlocklist`'s own
    docstring). `InProcessTokenBlocklist` never raises; it has no
    failure mode of its own.
    """

    async def revoke(self, jti: str, *, ttl_seconds: float) -> None: ...

    async def is_revoked(self, jti: str) -> bool: ...


class InProcessTokenBlocklist:
    """In-process fallback — a `jti -> expires_at` dict, lazily swept."""

    def __init__(self) -> None:
        self._revoked: dict[str, float] = {}

    async def revoke(self, jti: str, *, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return  # already expired; nothing to block
        self._revoked[jti] = time.monotonic() + ttl_seconds
        self._maybe_prune()

    async def is_revoked(self, jti: str) -> bool:
        expires_at = self._revoked.get(jti)
        if expires_at is None:
            return False
        if expires_at <= time.monotonic():
            del self._revoked[jti]
            return False
        return True

    def _maybe_prune(self) -> None:
        """Same coarse, bounded approach as `TokenBucketRateLimiter
        ._maybe_prune`/`LoginLockoutTracker._maybe_prune` — an entry here
        is a raw timestamp set once and read directly, never a
        lazily-recomputed derived value, so (unlike the rate limiter's
        own first attempt) a straightforward expiry comparison is
        actually correct."""
        if len(self._revoked) <= 10_000:
            return
        now = time.monotonic()
        stale = [jti for jti, expires_at in self._revoked.items() if expires_at <= now]
        for jti in stale:
            del self._revoked[jti]


class RedisTokenBlocklist:
    """Redis-backed — `SET ... EX <ttl>`, checked via `EXISTS`, with an
    internal `InProcessTokenBlocklist` written through to on every
    `revoke()` — see this module's own docstring for why (fail-closed,
    not open, on the residual case neither source can answer).

    No manual pruning against Redis itself: its own key expiry (the
    whole reason this task exists — see `app.core.redis`'s own module
    docstring) removes an entry automatically once its TTL elapses. The
    internal fallback still prunes itself the ordinary in-process way.
    """

    def __init__(self, client: redis.Redis) -> None:
        self._client = client
        self._fallback = InProcessTokenBlocklist()

    async def revoke(self, jti: str, *, ttl_seconds: float) -> None:
        # Written through unconditionally, *before* the Redis attempt —
        # a single-instance deployment must never lose track of a
        # revocation it just issued, even if this very Redis call is
        # what fails.
        await self._fallback.revoke(jti, ttl_seconds=ttl_seconds)
        if ttl_seconds <= 0:
            return
        try:
            await self._client.set(f"auth:revoked:{jti}", "1", ex=int(ttl_seconds) + 1)
        except Exception:
            logger.warning(
                "Redis unreachable revoking token %s; recorded in-process only "
                "until Redis recovers (durable record missing until then)",
                jti,
            )

    async def is_revoked(self, jti: str) -> bool:
        # The local write-through copy first: cheap, no I/O, and
        # complete for anything revoked during this process's own
        # lifetime — the only kind of revocation that exists today.
        if await self._fallback.is_revoked(jti):
            return True
        try:
            return bool(await self._client.exists(f"auth:revoked:{jti}"))
        except Exception:
            logger.error(
                "Redis unreachable checking revocation for token %s and no local "
                "record exists (revoked, if at all, before this process started) "
                "— failing closed, not open",
                jti,
            )
            raise RevocationCheckUnavailableError() from None


def build_token_blocklist(client: redis.Redis | None) -> TokenBlocklist:
    """`RedisTokenBlocklist` when `client` is available (a configured,
    reachable-at-startup Redis — see `app.core.redis`), else the
    in-process fallback."""
    if client is not None:
        return RedisTokenBlocklist(client)
    return InProcessTokenBlocklist()
