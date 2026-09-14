"""General inbound rate limiting (M5-E2-T1, Redis-backed since M5-E3-T1).

Two backends behind one `RateLimiter` interface — `allow(key)`, async on
both so `RateLimitMiddleware` never needs to know which one it's
talking to:

- `TokenBucketRateLimiter` — in-process, the original M5-E2-T1
  implementation and the fallback when `REDIS_URL` is unset. Made async
  here purely so its interface matches the Redis-backed one exactly; it
  performs no actual I/O and never awaits anything.
- `RedisTokenBucketRateLimiter` — the same token-bucket algorithm,
  evaluated atomically inside Redis via a single Lua script (`EVAL`),
  so a burst of concurrent requests for the same key can't race past
  each other the way two unsynchronized read-then-write round trips
  could. Every key carries its own TTL, so Redis's own expiry replaces
  `TokenBucketRateLimiter._maybe_prune`'s manual sweep entirely — no
  separate pruning step exists on this path (see `ARCHITECTURE.md` §
  "Redis" for the full reasoning, including why that manual prune had a
  real bug the first time, caught by its own test).

Both live on `app.state`, created fresh per `create_app()` call rather
than as a module-level singleton — a module-level tracker would leak
rate-limit state across the hundreds of independent `FastAPI` app
instances this test suite creates in the same process.

Deliberately separate from `app.auth.login_lockout`'s dedicated
brute-force defense on `POST /auth/login` — this is general fair-use
throttling across the whole API, not an account-security mechanism.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import redis.asyncio as redis
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.auth.security import decode_access_token
from app.core.config import Settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

#: Requests to these exact paths are never rate-limited — liveness checks
#: (used by orchestration/health probes, which must never be throttled)
#: and the versioned equivalent. Everything else, including every other
#: `/api/v1/system/*` endpoint, is limited like any other request.
_EXEMPT_PATHS = frozenset({"/health", "/api/v1/health"})


class RateLimiter(Protocol):
    async def allow(self, key: str) -> tuple[bool, float]: ...


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketRateLimiter:
    """A per-key token bucket — `capacity` tokens, refilling continuously
    over `window_seconds`, so a burst up to `capacity` is always allowed
    immediately and the *sustained* rate is what's actually bounded
    (never a hard reset-to-zero-every-window cliff).

    `clock` is injectable so tests can control time exactly rather than
    sleeping in real time — the same reasoning this platform's own
    deterministic `wait_for_in_flight_training_jobs` test helper follows
    for background tasks.
    """

    def __init__(
        self,
        *,
        capacity: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capacity = capacity
        self._window_seconds = window_seconds
        self._refill_rate = capacity / window_seconds
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    async def allow(self, key: str) -> tuple[bool, float]:
        """Consume one token for `key` if available.

        Returns `(True, 0.0)` when allowed, or `(False, retry_after)`
        with the number of seconds until at least one token is available.
        `async` purely to match `RedisTokenBucketRateLimiter`'s own
        interface — nothing here ever actually awaits.
        """
        now = self._clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = _Bucket(tokens=self._capacity - 1, last_refill=now)
            self._maybe_prune(now)
            return True, 0.0

        elapsed = max(0.0, now - bucket.last_refill)
        bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_rate)
        bucket.last_refill = now

        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return True, 0.0

        retry_after = (1 - bucket.tokens) / self._refill_rate
        return False, retry_after

    def _maybe_prune(self, now: float) -> None:
        """Drop fully-idle buckets once tracked keys pass a coarse bound.

        Staleness is judged purely by elapsed time since `last_refill`
        (`>= window_seconds`, i.e. long enough that the bucket would be
        back to full capacity even though nothing recomputed it) —
        deliberately *not* by comparing the stored `tokens` field against
        `capacity`. That field is only ever updated as a side effect of a
        later `allow()` call for the *same* key; a bucket touched exactly
        once (the common case for a one-off visitor) keeps its
        `capacity - 1` value frozen forever and would never look "full"
        by that measure no matter how much real time passed, making such
        a bucket permanently unprunable — exactly the unbounded-growth
        case this method exists to prevent.

        Cheap and approximate on purpose otherwise: this is a
        single-instance, in-process limiter, not a precision cache — the
        goal is only to stop unbounded memory growth from a very large
        number of distinct IPs over a long uptime, not to evict
        optimally. (The Redis-backed limiter needs no equivalent — see
        this module's own docstring.)
        """
        if len(self._buckets) <= 10_000:
            return
        stale = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.last_refill >= self._window_seconds
        ]
        for key in stale:
            del self._buckets[key]


#: Atomic token-bucket check-and-consume. KEYS[1] is the bucket's own
#: Redis key (a hash: tokens, last_refill); ARGV is capacity,
#: refill_rate (tokens/sec), now, and the TTL to set on the key (long
#: enough that an idle bucket would already be back at full capacity
#: before Redis ever expires it, so expiry never truncates a real
#: refill in progress). Returns {allowed (0/1), retry_after (string,
#: for float precision — Lua's own number-to-Redis-reply conversion
#: truncates to an integer)}.
_TOKEN_BUCKET_SCRIPT = """
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local data = redis.call("HMGET", KEYS[1], "tokens", "last_refill")
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
  tokens = capacity
  last_refill = now
end

local elapsed = now - last_refill
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
local retry_after = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry_after = (1 - tokens) / refill_rate
end

redis.call("HSET", KEYS[1], "tokens", tokens, "last_refill", now)
redis.call("EXPIRE", KEYS[1], ttl)

return {allowed, tostring(retry_after)}
"""


class RedisTokenBucketRateLimiter:
    """The same token-bucket algorithm as `TokenBucketRateLimiter`,
    evaluated atomically in Redis via `_TOKEN_BUCKET_SCRIPT` — a single
    `EVAL` round trip does the read, refill, consume, and write, so
    concurrent requests for the same key can't race each other the way
    two separate read-then-write calls could.

    **On a Redis error, delegates to an internal `TokenBucketRateLimiter`
    fallback instance — never a bare "allow everything".** The fallback
    is a complete, independently correct limiter (the same algorithm,
    just scoped to this process rather than shared/durable across
    restarts), so a Redis outage — including one caused by, or
    coinciding with, an actual abuse burst — degrades to single-
    instance-scoped throttling, never to no throttling at all. See
    `ARCHITECTURE.md` § "Redis" → "Mid-runtime failure handling".
    """

    def __init__(
        self,
        client: redis.Redis,
        *,
        capacity: int,
        window_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._capacity = capacity
        self._window_seconds = window_seconds
        self._refill_rate = capacity / window_seconds
        self._clock = clock
        self._script = client.register_script(_TOKEN_BUCKET_SCRIPT)
        self._fallback = TokenBucketRateLimiter(capacity=capacity, window_seconds=window_seconds)

    async def allow(self, key: str) -> tuple[bool, float]:
        try:
            allowed, retry_after = await self._script(
                keys=[f"ratelimit:{key}"],
                args=[
                    self._capacity,
                    self._refill_rate,
                    self._clock(),
                    # A generous TTL — long enough the bucket is provably
                    # back at full capacity before Redis would ever
                    # expire it, so expiry never truncates a real refill.
                    int(self._window_seconds * 2) + 1,
                ],
            )
        except Exception:
            logger.warning(
                "Redis unreachable for rate limit key %s; using in-process fallback "
                "(still enforced, just not the durable Redis-backed limit)",
                key,
            )
            return await self._fallback.allow(key)
        return bool(int(allowed)), float(retry_after)


def build_rate_limiter(client: redis.Redis | None, settings: Settings) -> RateLimiter:
    """`RedisTokenBucketRateLimiter` when `client` is available (a
    configured, reachable-at-startup Redis — see `app.core.redis`), else
    the in-process fallback."""
    if client is not None:
        return RedisTokenBucketRateLimiter(
            client,
            capacity=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
    return TokenBucketRateLimiter(
        capacity=settings.rate_limit_requests, window_seconds=settings.rate_limit_window_seconds
    )


def _resolve_key(request: Request, settings: Settings) -> str:
    """Prefer the authenticated user's id (a real login is a stronger,
    more precise identity than a shared/rotating IP); fall back to the
    client IP for an anonymous request or an invalid/expired token.

    Never raises — an invalid token here just means "treat this request
    as anonymous," the same as a request with no `Authorization` header
    at all. The actual auth check (`get_current_user`) still runs
    downstream and still rejects it properly; this is only choosing a
    rate-limit bucket, not authenticating anything. (Revocation is
    deliberately not checked here either — a revoked-but-structurally-
    valid token still keys by its own real subject, which is fine: the
    request itself will still be rejected downstream by `get_current_user`.)
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[len("bearer ") :].strip()
        try:
            claims = decode_access_token(token, settings=settings)
            return f"user:{claims.user_id}"
        except AppError:
            pass
    client = request.client
    ip = client.host if client is not None else "unknown"
    return f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies `request.app.state.rate_limiter` to every request except
    `_EXEMPT_PATHS` and CORS preflight (`OPTIONS`), returning a real
    `429` with a `Retry-After` header when a key's bucket is empty."""

    def __init__(self, app: object, *, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            not self._settings.rate_limit_enabled
            or request.method == "OPTIONS"
            or request.url.path in _EXEMPT_PATHS
        ):
            return await call_next(request)

        limiter: RateLimiter = request.app.state.rate_limiter
        key = _resolve_key(request, self._settings)
        allowed, retry_after = await limiter.allow(key)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"code": "rate_limited", "detail": "Too many requests"},
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        return await call_next(request)
