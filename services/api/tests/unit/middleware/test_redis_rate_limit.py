"""Tests for `RedisTokenBucketRateLimiter` (M5-E3-T1) against a real
Redis instance — never mocked, matching this task's own explicit
requirement. `TestTokenBucketRateLimiter` in `test_rate_limit.py` covers
the same external behavior for the in-process fallback; this file exists
specifically to prove the Redis-backed implementation of `allow` behaves
identically (same token-bucket algorithm, evaluated atomically via a Lua
script — see `app.middleware.rate_limit`'s own module docstring) and
that Redis's own key expiry does the pruning job manually done
in-process.
"""

import asyncio

import pytest
import redis.asyncio as redis

from app.middleware.rate_limit import RedisTokenBucketRateLimiter

pytestmark = pytest.mark.redis


class TestRedisTokenBucketRateLimiter:
    async def test_a_fresh_key_is_allowed(self, redis_client: redis.Redis) -> None:
        limiter = RedisTokenBucketRateLimiter(redis_client, capacity=5, window_seconds=60)
        allowed, retry_after = await limiter.allow("ip:1.2.3.4")
        assert allowed is True
        assert retry_after == 0.0

    async def test_exhausting_the_capacity_rejects_the_next_request(
        self, redis_client: redis.Redis
    ) -> None:
        limiter = RedisTokenBucketRateLimiter(redis_client, capacity=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = await limiter.allow("ip:1.2.3.4")
            assert allowed is True
        allowed, retry_after = await limiter.allow("ip:1.2.3.4")
        assert allowed is False
        assert retry_after > 0

    async def test_two_different_keys_have_independent_buckets(
        self, redis_client: redis.Redis
    ) -> None:
        limiter = RedisTokenBucketRateLimiter(redis_client, capacity=1, window_seconds=60)
        assert (await limiter.allow("ip:1.1.1.1"))[0] is True
        assert (await limiter.allow("ip:1.1.1.1"))[0] is False
        assert (await limiter.allow("ip:2.2.2.2"))[0] is True

    async def test_tokens_refill_over_real_elapsed_time(self, redis_client: redis.Redis) -> None:
        """A short, real window (no fake clock here — this proves the
        Lua script's own `now` computation against Redis's real state,
        not a mocked one) so the test doesn't need to wait long."""
        limiter = RedisTokenBucketRateLimiter(redis_client, capacity=1, window_seconds=1)
        assert (await limiter.allow("ip:refill-test"))[0] is True
        assert (await limiter.allow("ip:refill-test"))[0] is False
        await asyncio.sleep(1.1)
        assert (await limiter.allow("ip:refill-test"))[0] is True

    async def test_concurrent_requests_for_the_same_key_never_over_allow(
        self, redis_client: redis.Redis
    ) -> None:
        """The whole reason this is a single atomic Lua script, not a
        separate read-then-write: proves 20 concurrent callers sharing a
        5-token bucket get exactly 5 allowed, not more (which a
        non-atomic read/modify/write under real concurrency could)."""
        limiter = RedisTokenBucketRateLimiter(redis_client, capacity=5, window_seconds=60)
        results = await asyncio.gather(*(limiter.allow("ip:concurrent") for _ in range(20)))
        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count == 5

    async def test_a_bucket_key_expires_in_redis_on_its_own_no_manual_prune_needed(
        self, redis_client: redis.Redis
    ) -> None:
        """Redis's own TTL replaces `TokenBucketRateLimiter._maybe_prune`'s
        manual sweep entirely on this path — confirmed by checking the
        key actually carries a TTL, not just that requests succeed."""
        limiter = RedisTokenBucketRateLimiter(redis_client, capacity=5, window_seconds=10)
        await limiter.allow("ip:ttl-test")
        ttl = await redis_client.ttl("ratelimit:ip:ttl-test")
        assert ttl > 0

    async def test_a_mid_runtime_redis_failure_falls_back_to_a_real_in_process_limit(
        self,
    ) -> None:
        """Connects to a port nothing is listening on to force a real
        connection failure on every call — not a mock, an actual
        unreachable Redis. The first calls still succeed (the in-process
        fallback starts with a full bucket), but the fallback's *own*
        capacity is genuinely enforced once exhausted — this must never
        degrade to unconditionally allowing every request, only to a
        real, independently-functioning limiter scoped to this process.
        """
        unreachable = redis.from_url(
            "redis://localhost:1", socket_connect_timeout=1, decode_responses=True
        )
        limiter = RedisTokenBucketRateLimiter(unreachable, capacity=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = await limiter.allow("ip:whatever")
            assert allowed is True
        # The fallback's own 3-token bucket is now exhausted — this must
        # be rejected, proving the degraded mode still limits, not "any
        # Redis error means allow".
        allowed, retry_after = await limiter.allow("ip:whatever")
        assert allowed is False
        assert retry_after > 0
        await unreachable.aclose()
