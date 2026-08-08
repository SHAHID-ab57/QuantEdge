"""Top-level API router aggregation.

Mounted at both the root (for the unversioned /health endpoint) and under
/api/v1 (for the versioned API surface).
"""

from fastapi import APIRouter

from app.api.v1.router import router as v1_router

api_router = APIRouter()
api_router.include_router(v1_router, prefix="/api/v1")
api_router.include_router(v1_router, prefix="")
