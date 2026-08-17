"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.market_data import router as market_data_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(market_data_router)
