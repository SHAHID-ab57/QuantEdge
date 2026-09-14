"""Unit tests for `TokenBucketRateLimiter` (M5-E2-T1) — a fake, injectable
clock throughout, never a real sleep, so these are fast and deterministic.

`allow` is `async` (to match `RedisTokenBucketRateLimiter`'s own
interface — see `app.middleware.rate_limit`'s module docstring), though
nothing here ever actually awaits; `asyncio_mode = "auto"`
(`pyproject.toml`) runs these `async def` tests with no extra marker.
`tests/unit/middleware/test_redis_rate_limit.py` covers the Redis-backed
implementation against a real Redis instance.
"""

from app.middleware.rate_limit import TokenBucketRateLimiter


class FakeClock:
    """A controllable monotonic clock — `advance(seconds)` moves it
    forward explicitly, matching this platform's own "inject the clock,
    never sleep in a test" convention (see `app.auth.login_lockout`'s
    identical approach)."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestTokenBucketRateLimiter:
    async def test_a_fresh_key_is_allowed(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=5, window_seconds=60, clock=clock)
        allowed, retry_after = await limiter.allow("ip:1.2.3.4")
        assert allowed is True
        assert retry_after == 0.0

    async def test_exhausting_the_capacity_rejects_the_next_request(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=3, window_seconds=60, clock=clock)
        for _ in range(3):
            allowed, _ = await limiter.allow("ip:1.2.3.4")
            assert allowed is True
        allowed, retry_after = await limiter.allow("ip:1.2.3.4")
        assert allowed is False
        assert retry_after > 0

    async def test_two_different_keys_have_independent_buckets(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=1, window_seconds=60, clock=clock)
        assert (await limiter.allow("ip:1.1.1.1"))[0] is True
        assert (await limiter.allow("ip:1.1.1.1"))[0] is False
        # A second, unrelated key is unaffected by the first key's own exhaustion.
        assert (await limiter.allow("ip:2.2.2.2"))[0] is True

    async def test_tokens_refill_continuously_over_the_window(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=2, window_seconds=10, clock=clock)
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        assert (await limiter.allow("ip:1.2.3.4"))[0] is False

        # Half the window elapses — half the capacity (1 token) refills.
        clock.advance(5.0)
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        assert (await limiter.allow("ip:1.2.3.4"))[0] is False

    async def test_a_full_window_elapsing_restores_full_capacity(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=2, window_seconds=10, clock=clock)
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        assert (await limiter.allow("ip:1.2.3.4"))[0] is False

        clock.advance(10.0)
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        assert (await limiter.allow("ip:1.2.3.4"))[0] is False

    async def test_retry_after_reflects_time_until_the_next_token(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=1, window_seconds=10, clock=clock)
        assert (await limiter.allow("ip:1.2.3.4"))[0] is True
        _, retry_after = await limiter.allow("ip:1.2.3.4")
        # One token every 10 seconds — a fully-drained bucket needs the
        # full window before its next token is available.
        assert 9.0 < retry_after <= 10.0

    async def test_idle_buckets_are_pruned_once_the_tracker_grows_large(self) -> None:
        """Without this, every distinct IP/user that ever made one request
        stays resident for the life of the process — an unbounded dict."""
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=5, window_seconds=1, clock=clock)
        for i in range(10_001):
            await limiter.allow(f"ip:10.0.{i // 256}.{i % 256}")
        clock.advance(2.0)  # every bucket above is now fully refilled and idle
        # One more request (a real, current key) triggers the opportunistic
        # prune inside `allow` itself.
        await limiter.allow("ip:current")
        assert len(limiter._buckets) < 10_001, (
            "idle buckets were never pruned — the limiter grows unbounded"
        )
