"""Bearer token validation on a protected endpoint (`GET /auth/me`) — a
valid token is accepted; a missing, malformed, wrong-signature, or expired
one is rejected with a real 401, never a silent pass-through.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from app.models import User
from tests.auth.conftest import TEST_JWT_SECRET


@pytest.mark.asyncio
class TestValidToken:
    async def test_a_freshly_issued_valid_token_is_accepted(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str], registered_user: User
    ) -> None:
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == str(registered_user.id)


@pytest.mark.asyncio
class TestInvalidToken:
    async def test_no_authorization_header_at_all_is_rejected(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["code"] == "authentication_required"

    async def test_a_malformed_token_is_rejected(self, client: httpx.AsyncClient) -> None:
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-jwt-at-all"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_token"

    async def test_a_token_signed_with_the_wrong_secret_is_rejected(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        now = datetime.now(UTC)
        forged = jwt.encode(
            {"sub": str(registered_user.id), "iat": now, "exp": now + timedelta(minutes=60)},
            "a-completely-different-secret-that-is-at-least-32-bytes-long",
            algorithm="HS256",
        )
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_token"

    async def test_an_expired_token_is_rejected_with_its_own_distinct_error(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        now = datetime.now(UTC)
        expired = jwt.encode(
            {
                "sub": str(registered_user.id),
                "iat": now - timedelta(minutes=120),
                "exp": now - timedelta(minutes=60),
            },
            TEST_JWT_SECRET,
            algorithm="HS256",
        )
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "token_expired"

    async def test_a_token_naming_a_user_id_that_does_not_exist_is_rejected(
        self, client: httpx.AsyncClient
    ) -> None:
        now = datetime.now(UTC)
        token = jwt.encode(
            {"sub": str(uuid.uuid4()), "iat": now, "exp": now + timedelta(minutes=60)},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_token"

    async def test_a_token_with_no_subject_claim_is_rejected(
        self, client: httpx.AsyncClient
    ) -> None:
        now = datetime.now(UTC)
        token = jwt.encode(
            {"iat": now, "exp": now + timedelta(minutes=60)}, TEST_JWT_SECRET, algorithm="HS256"
        )
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_token"
