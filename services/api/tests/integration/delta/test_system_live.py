"""Live integration tests for the platform system endpoints.

Requires ``--run-integration``: probes the real Delta REST API with a
short timeout. No database or credentials are needed for these tests.
"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.runtime import Runtime, get_runtime


def _offline_runtime() -> Runtime:
    """Build a runtime with no live components for probe testing."""
    return Runtime(
        market_data_live=False,
        symbols=(),
        started_at=datetime.now(UTC),
    )


@pytest.mark.integration
async def test_system_health_delta_rest_reachable(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """The live Delta REST probe reports reachable with a latency."""
    app.dependency_overrides[get_runtime] = lambda: _offline_runtime()
    try:
        response = await client.get("/api/v1/system/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["delta_rest"]["status"] == "ok"
    assert body["delta_rest"]["detail"].startswith("reachable")
    assert "ms" in body["delta_rest"]["detail"]


@pytest.mark.integration
async def test_system_probe_direct() -> None:
    """The probe itself returns a structured, non-raising result."""
    result = await _offline_runtime().probe_delta_rest()
    assert result.ok is True
    assert result.error is None
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


@pytest.mark.integration
async def test_system_status_tracks_rest_timeline(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """The status timeline records the last REST probe time."""
    runtime = _offline_runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        await client.get("/api/v1/system/health")
        body = (await client.get("/api/v1/system/status")).json()
    finally:
        app.dependency_overrides.clear()
    assert body["last_rest_request_at"] is not None