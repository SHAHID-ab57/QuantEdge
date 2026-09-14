"""Tests for `RedisLoginLockoutTracker` (M5-E3-T1) against a real Redis
instance — never mocked. `TestLoginLockoutTrackerUnit` in
`test_login_lockout.py` covers the same external behavior for the
in-process fallback; this file proves the Redis-backed implementation
(the same attempt-count/window/cooldown algorithm, evaluated atomically
via a Lua script) behaves identically, and that concurrent failures for
the same key can't race past `max_attempts`.
"""

import asyncio

import pytest
import redis.asyncio as redis

from app.auth.login_lockout import RedisLoginLockoutTracker

pytestmark = pytest.mark.redis


class TestRedisLoginLockoutTracker:
    async def test_a_fresh_key_is_never_locked(self, redis_client: redis.Redis) -> None:
        tracker = RedisLoginLockoutTracker(
            redis_client, max_attempts=3, window_seconds=60, cooldown_seconds=300
        )
        assert await tracker.seconds_locked("email:nobody@example.com") == 0.0

    async def test_fewer_than_max_attempts_does_not_lock(self, redis_client: redis.Redis) -> None:
        tracker = RedisLoginLockoutTracker(
            redis_client, max_attempts=3, window_seconds=60, cooldown_seconds=300
        )
        assert await tracker.record_failure("email:x") is False
        assert await tracker.record_failure("email:x") is False
        assert await tracker.seconds_locked("email:x") == 0.0

    async def test_the_max_attempt_th_failure_locks_and_returns_true_exactly_once(
        self, redis_client: redis.Redis
    ) -> None:
        tracker = RedisLoginLockoutTracker(
            redis_client, max_attempts=3, window_seconds=60, cooldown_seconds=300
        )
        assert await tracker.record_failure("email:x") is False
        assert await tracker.record_failure("email:x") is False
        assert await tracker.record_failure("email:x") is True
        assert await tracker.seconds_locked("email:x") == pytest.approx(300.0, abs=2)

    async def test_success_clears_the_failure_count(self, redis_client: redis.Redis) -> None:
        tracker = RedisLoginLockoutTracker(
            redis_client, max_attempts=3, window_seconds=60, cooldown_seconds=300
        )
        await tracker.record_failure("email:x")
        await tracker.record_failure("email:x")
        await tracker.record_success("email:x")
        await tracker.record_failure("email:x")
        await tracker.record_failure("email:x")
        assert await tracker.seconds_locked("email:x") == 0.0

    async def test_two_different_keys_are_tracked_independently(
        self, redis_client: redis.Redis
    ) -> None:
        tracker = RedisLoginLockoutTracker(
            redis_client, max_attempts=2, window_seconds=60, cooldown_seconds=300
        )
        await tracker.record_failure("email:a@example.com")
        await tracker.record_failure("email:a@example.com")
        assert await tracker.seconds_locked("email:a@example.com") > 0
        assert await tracker.seconds_locked("email:b@example.com") == 0.0

    async def test_a_lockout_key_carries_a_ttl_no_manual_prune_needed(
        self, redis_client: redis.Redis
    ) -> None:
        tracker = RedisLoginLockoutTracker(
            redis_client, max_attempts=2, window_seconds=60, cooldown_seconds=300
        )
        await tracker.record_failure("email:ttl-test")
        ttl = await redis_client.ttl("lockout:email:ttl-test")
        assert ttl > 0

    async def test_concurrent_failures_never_lock_out_more_than_once(
        self, redis_client: redis.Redis
    ) -> None:
        """Proves the Lua script's atomicity: 10 concurrent failures
        against a 3-attempt limit must cross the threshold exactly once,
        not race into reporting `just_locked=True` multiple times."""
        tracker = RedisLoginLockoutTracker(
            redis_client, max_attempts=3, window_seconds=60, cooldown_seconds=300
        )
        results = await asyncio.gather(
            *(tracker.record_failure("email:concurrent") for _ in range(10))
        )
        assert sum(1 for just_locked in results if just_locked) == 1

    async def test_a_mid_runtime_redis_failure_still_locks_out_via_the_fallback(
        self,
    ) -> None:
        """Connects to a port nothing is listening on to force a real,
        sustained connection failure on every call. Directly answers the
        "attacker benefits from Redis instability" scenario: the fallback
        must genuinely enforce `max_attempts`, not just silently permit
        every attempt — 2 failures stay unlocked, the 3rd (crossing
        `max_attempts=3`) locks it out for real, exactly as the
        real Redis-backed path would.
        """
        unreachable = redis.from_url(
            "redis://localhost:1", socket_connect_timeout=1, decode_responses=True
        )
        tracker = RedisLoginLockoutTracker(
            unreachable, max_attempts=3, window_seconds=60, cooldown_seconds=300
        )
        assert await tracker.seconds_locked("email:x") == 0.0
        assert await tracker.record_failure("email:x") is False
        assert await tracker.record_failure("email:x") is False
        assert await tracker.record_failure("email:x") is True  # crosses max_attempts
        assert await tracker.seconds_locked("email:x") > 0
        await tracker.record_success("email:x")  # must not raise
        assert await tracker.seconds_locked("email:x") == 0.0
        await unreachable.aclose()
