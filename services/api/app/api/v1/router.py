"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints.features import router as features_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.indicators import router as indicators_router
from app.api.v1.endpoints.market_data import router as market_data_router
from app.api.v1.endpoints.market_stream import router as market_stream_router
from app.api.v1.endpoints.system import router as system_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(features_router)
router.include_router(indicators_router)
router.include_router(market_data_router)
router.include_router(market_stream_router)
router.include_router(system_router)
