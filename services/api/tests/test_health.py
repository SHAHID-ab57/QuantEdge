"""Smoke tests for the health endpoints."""

from fastapi.testclient import TestClient

from app.application import create_app

client = TestClient(create_app())


def test_health_root() -> None:
    """The unversioned /health endpoint returns service metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api", "version": "0.1.0"}


def test_health_versioned() -> None:
    """The versioned /api/v1/health endpoint returns service metadata."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api", "version": "0.1.0"}
