"""Response schemas for the health endpoint."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Service health and version metadata."""

    status: str
    service: str
    version: str
    database: str
