"""The concrete Definition-of-Done proof for M5-E1-T1's own motivating
incident: a real, logged-in user flips `strategy_enabled` on a paper
account, and `GET /audit-log` shows exactly who did it and when — not
just that the value changed (already true before this task, via
`app/services/paper_trading.py`'s own LOG-ACCOUNT-CONFIG-CHANGES lines),
but a real, queryable, attributable row naming the actual user.

Goes through a real login (`POST /auth/login`) end to end, never
`create_access_token` directly, so this is the same path a real user
takes — not a shortcut around it.
"""

import httpx
import pytest

from app.models import User
from tests.conftest import SessionFactory
from tests.prediction.test_service import train_completed_job


async def _login(client: httpx.AsyncClient, *, email: str, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestAuditTrailAttributesAStrategyEnabledChange:
    async def test_enabling_the_strategy_records_which_user_did_it(
        self,
        client: httpx.AsyncClient,
        session_factory: SessionFactory,
        registered_user: User,
    ) -> None:
        headers = await _login(
            client, email=registered_user.email, password="correct-horse-battery-staple"
        )
        job_id, _ = await train_completed_job(
            session_factory, symbol="AUDITSTRATUSD", model_type="logistic_regression"
        )

        account = (
            await client.post(
                "/api/v1/paper-trading/accounts",
                json={"starting_balance": "100000"},
                headers=headers,
            )
        ).json()

        patched = await client.patch(
            f"/api/v1/paper-trading/accounts/{account['id']}/strategy",
            json={
                "enabled": True,
                "training_job_id": job_id,
                "confidence_threshold_pct": "70",
                "default_stop_loss_pct": "8",
            },
            headers=headers,
        )
        assert patched.status_code == 200
        assert patched.json()["strategy_enabled"] is True

        audit = await client.get(
            "/api/v1/audit-log",
            params={"resource_type": "paper_account", "resource_id": account["id"]},
            headers=headers,
        )
        assert audit.status_code == 200
        entries = audit.json()["entries"]

        enabled_entries = [e for e in entries if e["action"] == "paper_account.strategy_enabled"]
        assert len(enabled_entries) == 1, entries
        entry = enabled_entries[0]

        # Who: the real, logged-in user — not a placeholder, not None.
        assert entry["user_id"] == str(registered_user.id)
        # What: the resource this mutation actually touched.
        assert entry["resource_type"] == "paper_account"
        assert entry["resource_id"] == account["id"]
        # When: a real timestamp was recorded, not left null.
        assert entry["created_at"]
        # The old/new snapshot itself proves this is the enable transition,
        # not merely that some row with this action string exists.
        assert entry["old_value"]["enabled"] is False
        assert entry["new_value"]["enabled"] is True
        assert entry["new_value"]["training_job_id"] == job_id

        # The account-creation mutation is independently attributed too —
        # this is a general capability, not a one-off special case for
        # `strategy_enabled`.
        create_entries = [e for e in entries if e["action"] == "paper_account.create"]
        assert len(create_entries) == 1
        assert create_entries[0]["user_id"] == str(registered_user.id)

    async def test_a_second_user_never_appears_as_the_actor_for_the_firsts_change(
        self,
        client: httpx.AsyncClient,
        session_factory: SessionFactory,
        registered_user: User,
    ) -> None:
        """Attribution is to the real caller, not to whichever user happens
        to exist first, or to some shared default."""
        async with session_factory() as session:
            from app.auth.security import hash_password

            other = User(
                email="second-auth-suite-user@example.com",
                hashed_password=hash_password("a-different-password"),
            )
            session.add(other)
            await session.commit()
            await session.refresh(other)

        headers_a = await _login(
            client, email=registered_user.email, password="correct-horse-battery-staple"
        )
        headers_b = await _login(client, email=other.email, password="a-different-password")

        account = (
            await client.post(
                "/api/v1/paper-trading/accounts",
                json={"starting_balance": "50000"},
                headers=headers_a,
            )
        ).json()

        audit = await client.get(
            "/api/v1/audit-log",
            params={"resource_type": "paper_account", "resource_id": account["id"]},
            headers=headers_b,
        )
        entries = audit.json()["entries"]
        create_entries = [e for e in entries if e["action"] == "paper_account.create"]
        assert len(create_entries) == 1
        assert create_entries[0]["user_id"] == str(registered_user.id)
        assert create_entries[0]["user_id"] != str(other.id)
