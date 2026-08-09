"""Health endpoint.

Provides liveness, service metadata, and database connectivity checks.
"""

from fastapi import APIRouter, HTTPException, status

from app import __version__
from app.db.engine import probe_database
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health() -> HealthResponse:
    """Return service health, version, and database connectivity."""
    error = await probe_database()
    if error is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {error}",
        )
    return HealthResponse(
        status="ok",
        service="api",
        version=__version__,
        database="connected",
    )
