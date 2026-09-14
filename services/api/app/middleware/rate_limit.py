"""General inbound rate limiting (M5-E2-T1).

In-process only — no Redis or other distributed store yet, since this
platform runs a single instance (see `ARCHITECTURE.md` § "Rate
Limiting"). A `TokenBucketRateLimiter` instance lives on `app.state`,
created fresh per `create_app()` call rather than as a module-level
singleton — the same reasoning every other per-app resource on this
platform follows, and specifically important here: a module-level
tracker would leak rate-limit state across the hundreds of independent
`FastAPI` app instances this test suite creates in the same process.

Deliberately separate from `app.auth.login_lockout`'s dedicated
brute-force defense on `POST /auth/login` — this is general fair-use
throttling across the whole API, not an account-security mechanism.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.auth.security import decode_access_token
from app.core.config import Settings
from app.core.exceptions import AppError

#: Requests to these exact paths are never rate-limited — liveness checks
#: (used by orchestration/health probes, which must never be throttled)
#: and the versioned equivalent. Everything else, including every other
#: `/api/v1/system/*` endpoint, is limited like any other request.
_EXEMPT_PATHS = frozenset({"/health", "/api/v1/health"})


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

    def allow(self, key: str) -> tuple[bool, float]:
        """Consume one token for `key` if available.

        Returns `(True, 0.0)` when allowed, or `(False, retry_after)`
        with the number of seconds until at least one token is available.
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
        single-instance, in-process limiter (see this module's own
        docstring on why no distributed store exists yet), not a
        precision cache — the goal is only to stop unbounded memory
        growth from a very large number of distinct IPs over a long
        uptime, not to evict optimally.
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


def _resolve_key(request: Request, settings: Settings) -> str:
    """Prefer the authenticated user's id (a real login is a stronger,
    more precise identity than a shared/rotating IP); fall back to the
    client IP for an anonymous request or an invalid/expired token.

    Never raises — an invalid token here just means "treat this request
    as anonymous," the same as a request with no `Authorization` header
    at all. The actual auth check (`get_current_user`) still runs
    downstream and still rejects it properly; this is only choosing a
    rate-limit bucket, not authenticating anything.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[len("bearer ") :].strip()
        try:
            user_id = decode_access_token(token, settings=settings)
            return f"user:{user_id}"
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

        limiter: TokenBucketRateLimiter = request.app.state.rate_limiter
        key = _resolve_key(request, self._settings)
        allowed, retry_after = limiter.allow(key)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"code": "rate_limited", "detail": "Too many requests"},
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        return await call_next(request)
