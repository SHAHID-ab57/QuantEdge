"""Every mutating endpoint on this platform (plus the two read-only routes
that are still authenticated: `GET /auth/me` and `GET /audit-log`) rejects
an unauthenticated request with a real 401 — never a silent pass-through,
and never a 422 that would let a body-validation error mask a missing
token.

This is the direct DoD proof for M5-E1-T1's own framing: two real
incidents (leaked API keys, an unattributed `strategy_enabled` reversion)
happened because nothing on this platform required an identity. The list
below is every endpoint identified by reading each handler's own service
call in Step 1 of that task — 22 that persist a change, plus the two
always-authenticated read routes `auth.py` itself adds.

A placeholder UUID stands in for every path parameter and an empty JSON
body for every request body — `get_current_user` raises before either the
path lookup or body validation would ever run (confirmed empirically: an
empty body against a real route already returns 401, never 422), so
neither needs to be valid for this test to prove the auth boundary.
"""

import httpx
import pytest

_PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"

#: (method, path, expects_json_body) — one entry per endpoint identified in
#: Step 1 as requiring `Annotated[User, Depends(get_current_user)]`.
_PROTECTED_ENDPOINTS: list[tuple[str, str, bool]] = [
    # Paper Trading (app/api/v1/endpoints/paper_trading.py)
    ("POST", "/api/v1/paper-trading/accounts", True),
    ("POST", f"/api/v1/paper-trading/accounts/{_PLACEHOLDER_ID}/orders", True),
    ("POST", f"/api/v1/paper-trading/accounts/{_PLACEHOLDER_ID}/resume-trading", False),
    (
        "PATCH",
        f"/api/v1/paper-trading/accounts/{_PLACEHOLDER_ID}/positions/ETHUSD",
        True,
    ),
    ("PATCH", f"/api/v1/paper-trading/accounts/{_PLACEHOLDER_ID}/strategy", True),
    # Experiments (app/api/v1/endpoints/experiments.py)
    ("POST", "/api/v1/experiments", True),
    ("PATCH", f"/api/v1/experiments/{_PLACEHOLDER_ID}", True),
    ("DELETE", f"/api/v1/experiments/{_PLACEHOLDER_ID}", False),
    ("POST", f"/api/v1/experiments/{_PLACEHOLDER_ID}/metrics", True),
    ("DELETE", f"/api/v1/experiments/{_PLACEHOLDER_ID}/metrics/{_PLACEHOLDER_ID}", False),
    ("POST", f"/api/v1/experiments/{_PLACEHOLDER_ID}/artifacts", True),
    ("DELETE", f"/api/v1/experiments/{_PLACEHOLDER_ID}/artifacts/{_PLACEHOLDER_ID}", False),
    # ML Dataset Builder (app/api/v1/endpoints/ml_datasets.py)
    ("POST", "/api/v1/markets/ETHUSD/ml/dataset", True),
    ("DELETE", f"/api/v1/ml/dataset-builds/{_PLACEHOLDER_ID}", False),
    # Evaluation (app/api/v1/endpoints/evaluation.py)
    ("POST", "/api/v1/evaluation/benchmark", True),
    ("DELETE", f"/api/v1/evaluation/history/{_PLACEHOLDER_ID}", False),
    # Backtesting (app/api/v1/endpoints/backtest.py)
    ("POST", "/api/v1/backtests/run", True),
    # Training (app/api/v1/endpoints/training.py)
    ("POST", "/api/v1/training-jobs", True),
    ("DELETE", f"/api/v1/training-jobs/{_PLACEHOLDER_ID}", False),
    ("POST", f"/api/v1/training-jobs/{_PLACEHOLDER_ID}/run", False),
    ("POST", f"/api/v1/training-jobs/{_PLACEHOLDER_ID}/cancel", False),
    # Live Prediction Service (app/api/v1/endpoints/prediction.py)
    ("POST", "/api/v1/predictions/run", True),
    # Authentication & Audit Trail itself (app/api/v1/endpoints/auth.py) —
    # read-only, but still requires a real identity: an audit trail naming
    # who did what is itself sensitive.
    ("GET", "/api/v1/auth/me", False),
    ("GET", "/api/v1/audit-log", False),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,expects_body",
    _PROTECTED_ENDPOINTS,
    ids=[f"{m} {p}" for m, p, _ in _PROTECTED_ENDPOINTS],
)
async def test_an_unauthenticated_request_is_rejected_with_a_real_401(
    client: httpx.AsyncClient, method: str, path: str, expects_body: bool
) -> None:
    response = await client.request(method, path, json={} if expects_body else None)
    assert response.status_code == 401, (
        f"{method} {path} did not return 401 for an unauthenticated request "
        f"(got {response.status_code}: {response.text})"
    )
    assert response.json()["code"] in {"authentication_required", "invalid_token", "token_expired"}


@pytest.mark.asyncio
async def test_the_login_endpoint_itself_requires_no_authentication(
    client: httpx.AsyncClient,
) -> None:
    """The one deliberate exception — confirms the suite's own premise: every
    endpoint above is protected *because* it mutates or reads sensitive
    state, not because every route on this platform now requires a token."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"  # rejected on credentials, not auth
