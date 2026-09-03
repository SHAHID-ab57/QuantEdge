"""Smoke tests for the health endpoints."""

import httpx

from app.schemas.health import HealthResponse


async def test_health_root_unconfigured_database(
    client: httpx.AsyncClient,
) -> None:
    """Without a database, /health reports 503 with an error detail."""
    response = await client.get("/health")
    assert response.status_code == 503
    assert "Database unavailable" in response.json()["detail"]


async def test_health_versioned_unconfigured_database(
    client: httpx.AsyncClient,
) -> None:
    """Without a database, /api/v1/health reports 503 with an error detail."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    assert "Database unavailable" in response.json()["detail"]


async def test_health_response_shape() -> None:
    """The healthy response shape matches the documented contract."""
    response = HealthResponse(status="ok", service="api", version="0.1.0", database="connected")
    assert response.model_dump() == {
        "status": "ok",
        "service": "api",
        "version": "0.1.0",
        "database": "connected",
    }
