"""Shared dependency providers for the market data API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.services.market_data import MarketDataService


def get_market_data_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketDataService:
    """Build the market data service wired to the request session."""
    settings = get_settings()
    return MarketDataService(
        candle_repository=CandleRepository(session),
        market_repository=MarketRepository(session),
        default_limit=settings.candles_default_limit,
        max_limit=settings.candles_max_limit,
    )