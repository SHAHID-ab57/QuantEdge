"""Health endpoint.

Provides liveness and service metadata for the API service.
"""

from fastapi import APIRouter, status

from app import __version__
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health() -> HealthResponse:
    """Return service health and version information."""
    return HealthResponse(status="ok", service="api", version=__version__)
