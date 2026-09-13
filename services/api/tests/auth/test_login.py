"""`POST /auth/login` — issuing a real bearer token, and the two ways it
refuses to (unknown email, wrong password), both as the same
`invalid_credentials` error so neither can be used to enumerate accounts.
"""

import httpx
import jwt
import pytest

from app.models import User
from tests.auth.conftest import TEST_JWT_SECRET


@pytest.mark.asyncio
class TestLoginSuccess:
    async def test_logging_in_with_the_correct_password_issues_a_real_bearer_token(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert isinstance(body["expires_in"], int) and body["expires_in"] > 0
        assert isinstance(body["access_token"], str) and body["access_token"]

        # The issued token is a real, verifiable JWT naming this exact user.
        payload = jwt.decode(body["access_token"], TEST_JWT_SECRET, algorithms=["HS256"])
        assert payload["sub"] == str(registered_user.id)

    async def test_the_issued_token_actually_authenticates_a_protected_request(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "correct-horse-battery-staple"},
        )
        token = login.json()["access_token"]

        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == registered_user.email
        assert me.json()["id"] == str(registered_user.id)


@pytest.mark.asyncio
class TestLoginFailure:
    async def test_an_unknown_email_is_rejected(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-registered@example.com", "password": "whatever"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_credentials"

    async def test_the_wrong_password_for_a_real_user_is_rejected(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "definitely-not-it"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_credentials"

    async def test_unknown_email_and_wrong_password_return_the_identical_error(
        self, client: httpx.AsyncClient, registered_user: User
    ) -> None:
        """Never a distinguishable error — a login endpoint that says "no such
        user" for one and "wrong password" for the other hands an attacker a
        free username enumeration oracle."""
        unknown = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-registered@example.com", "password": "whatever"},
        )
        wrong_password = await client.post(
            "/api/v1/auth/login",
            json={"email": registered_user.email, "password": "definitely-not-it"},
        )
        assert unknown.status_code == wrong_password.status_code == 401
        assert unknown.json() == wrong_password.json()

    async def test_no_self_registration_endpoint_exists(self, client: httpx.AsyncClient) -> None:
        """First-user creation is deliberately a CLI-only path
        (`make create-user`) — no `POST /auth/register` or similar exists."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "whatever"},
        )
        assert response.status_code == 404
