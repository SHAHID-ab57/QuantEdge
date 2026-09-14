"""Token revocation (M5-E3-T1) — `InProcessTokenBlocklist` and
`RedisTokenBlocklist` in isolation, plus the real end-to-end proof this
task exists for: `TestRealReplayFromM5E1T1` repeats the *exact* replay
scenario M5-E1-T1's own live verification disclosed as a gap (issue a
token, "log out," replay the token) and asserts it is now rejected,
where before it was accepted.
"""

import asyncio

import httpx
import pytest
import redis.asyncio as redis
from fastapi import FastAPI

from app.auth.errors import RevocationCheckUnavailableError
from app.auth.token_revocation import InProcessTokenBlocklist, RedisTokenBlocklist
from app.dependencies.auth import get_token_blocklist
from app.models import User


class TestInProcessTokenBlocklist:
    async def test_a_fresh_jti_is_not_revoked(self) -> None:
        blocklist = InProcessTokenBlocklist()
        assert await blocklist.is_revoked("some-jti") is False

    async def test_revoking_a_jti_marks_it_revoked(self) -> None:
        blocklist = InProcessTokenBlocklist()
        await blocklist.revoke("some-jti", ttl_seconds=60)
        assert await blocklist.is_revoked("some-jti") is True

    async def test_a_zero_or_negative_ttl_is_a_no_op(self) -> None:
        """A token that's already (or about to be) expired needs no
        blocklist entry at all — it can't authenticate anything anyway."""
        blocklist = InProcessTokenBlocklist()
        await blocklist.revoke("already-expired", ttl_seconds=0)
        assert await blocklist.is_revoked("already-expired") is False

    async def test_natural_ttl_expiry_un_revokes_the_token(self) -> None:
        blocklist = InProcessTokenBlocklist()
        await blocklist.revoke("short-lived", ttl_seconds=0.2)
        assert await blocklist.is_revoked("short-lived") is True
        await asyncio.sleep(0.3)
        assert await blocklist.is_revoked("short-lived") is False

    async def test_two_different_tokens_are_tracked_independently(self) -> None:
        blocklist = InProcessTokenBlocklist()
        await blocklist.revoke("token-a", ttl_seconds=60)
        assert await blocklist.is_revoked("token-a") is True
        assert await blocklist.is_revoked("token-b") is False


@pytest.mark.redis
class TestRedisTokenBlocklist:
    async def test_a_fresh_jti_is_not_revoked(self, redis_client: redis.Redis) -> None:
        blocklist = RedisTokenBlocklist(redis_client)
        assert await blocklist.is_revoked("some-jti") is False

    async def test_revoking_a_jti_marks_it_revoked(self, redis_client: redis.Redis) -> None:
        blocklist = RedisTokenBlocklist(redis_client)
        await blocklist.revoke("some-jti", ttl_seconds=60)
        assert await blocklist.is_revoked("some-jti") is True

    async def test_natural_ttl_expiry_un_revokes_the_token(self, redis_client: redis.Redis) -> None:
        """`revoke` rounds its TTL *up* (`int(ttl_seconds) + 1`) rather
        than truncating down — safer to protect a fraction of a second
        too long than to expire early — so this waits past that
        rounded-up TTL, not the raw requested one."""
        blocklist = RedisTokenBlocklist(redis_client)
        await blocklist.revoke("short-lived", ttl_seconds=1)
        assert await blocklist.is_revoked("short-lived") is True
        await asyncio.sleep(2.5)
        assert await blocklist.is_revoked("short-lived") is False

    async def test_the_redis_key_itself_carries_the_ttl(self, redis_client: redis.Redis) -> None:
        blocklist = RedisTokenBlocklist(redis_client)
        await blocklist.revoke("ttl-check", ttl_seconds=60)
        ttl = await redis_client.ttl("auth:revoked:ttl-check")
        assert ttl > 0

    async def test_a_revocation_survives_a_mid_runtime_redis_failure_via_write_through(
        self,
    ) -> None:
        """The exact scenario a naive fail-open design gets wrong: revoke
        a real token, *then* Redis becomes unreachable, then someone
        replays it. The write-through to the internal in-process
        fallback (populated at `revoke()` time, while Redis was still
        healthy) must still catch it — a revoked token must never
        silently become valid again just because Redis blipped
        afterward.
        """
        unreachable = redis.from_url(
            "redis://localhost:1", socket_connect_timeout=1, decode_responses=True
        )
        blocklist = RedisTokenBlocklist(unreachable)
        # `revoke` itself tolerates the Redis failure (writes through to
        # the fallback regardless of whether the Redis half succeeds).
        await blocklist.revoke("mid-outage-revoked", ttl_seconds=60)
        assert await blocklist.is_revoked("mid-outage-revoked") is True
        await unreachable.aclose()

    async def test_fails_closed_not_open_when_neither_source_can_answer(self) -> None:
        """The genuine residual gap: a `jti` this process never revoked
        (so the write-through fallback has no record) queried while
        Redis is unreachable. Silently returning `False` here would mean
        "we don't know, so let's allow it" for a security check —
        unacceptable. Must raise, not pass through as valid."""
        unreachable = redis.from_url(
            "redis://localhost:1", socket_connect_timeout=1, decode_responses=True
        )
        blocklist = RedisTokenBlocklist(unreachable)
        with pytest.raises(RevocationCheckUnavailableError):
            await blocklist.is_revoked("never-seen-by-this-process")
        await unreachable.aclose()


@pytest.mark.asyncio
class TestRevocationCheckUnavailablePropagatesThroughTheRealEndpoint:
    async def test_a_request_is_rejected_503_not_silently_accepted(
        self, app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """`get_current_user` never catches `RevocationCheckUnavailableError`
        itself — it's expected to propagate straight through FastAPI's own
        `AppError` handler. Proven here through a real HTTP call, not just
        at the `TokenBlocklist` unit level: a valid, unexpired, genuinely
        unrevoked token still gets `503`, not `200`, when its revocation
        status can't be verified — the request is refused, never silently
        treated as authenticated.
        """

        class _AlwaysUnavailableBlocklist:
            async def revoke(self, jti: str, *, ttl_seconds: float) -> None:
                raise AssertionError("not exercised by this test")

            async def is_revoked(self, jti: str) -> bool:
                raise RevocationCheckUnavailableError()

        app.dependency_overrides[get_token_blocklist] = lambda: _AlwaysUnavailableBlocklist()
        try:
            response = await client.get("/api/v1/auth/me", headers=auth_headers)
        finally:
            del app.dependency_overrides[get_token_blocklist]

        assert response.status_code == 503
        assert response.json()["code"] == "revocation_check_unavailable"


@pytest.mark.asyncio
class TestRealReplayFromM5E1T1:
    async def test_issue_logout_replay_is_now_rejected(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        """M5-E1-T1's own live verification: a token captured before
        'logging out' was replayed against `GET /auth/me` and still
        returned `200` with the real user's profile — logout only ever
        cleared the token client-side. Repeating that *exact* scenario:
        issue a real token via `POST /auth/login`, call the new `POST
        /auth/logout`, then replay the identical token — must now be
        rejected, not accepted.
        """
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # The token is genuinely valid before logout.
        before = await client.get("/api/v1/auth/me", headers=headers)
        assert before.status_code == 200

        logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 204

        # Replay the *same* token — the exact scenario M5-E1-T1 found
        # still worked (200) before this task.
        replayed = await client.get("/api/v1/auth/me", headers=headers)
        assert replayed.status_code == 401
        assert replayed.json()["code"] == "token_revoked"

    async def test_logout_only_revokes_the_one_token_not_every_session(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        """Two separate logins (two separate `jti`s) for the same user;
        logging out of one must not invalidate the other."""
        login_a = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        login_b = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        token_a = login_a.json()["access_token"]
        token_b = login_b.json()["access_token"]
        assert token_a != token_b

        await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token_a}"})

        rejected = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"}
        )
        assert rejected.status_code == 401

        still_valid = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert still_valid.status_code == 200

    async def test_logging_out_twice_is_idempotent_not_an_error(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        first = await client.post("/api/v1/auth/logout", headers=headers)
        assert first.status_code == 204
        second = await client.post("/api/v1/auth/logout", headers=headers)
        assert second.status_code == 204

    async def test_logout_requires_authentication(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 401
        assert response.json()["code"] == "authentication_required"
