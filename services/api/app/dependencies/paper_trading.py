"""Dependency providers for the Paper Trading API."""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)
from app.runtime import Runtime, get_runtime
from app.services.paper_trading import PaperTradingService


def get_paper_trading_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    runtime: Annotated[Runtime, Depends(get_runtime)],
) -> PaperTradingService:
    """Build the paper trading service wired to the request session and
    the process-wide `MarketStateManager` — the identical live state
    `app/api/v1/endpoints/market_stream.py`'s own WebSocket gateway reads,
    never a second market-data path built for this feature alone.
    """
    settings = get_settings()
    return PaperTradingService(
        account_repository=PaperAccountRepository(session),
        order_repository=PaperOrderRepository(session),
        position_repository=PaperPositionRepository(session),
        market_repository=MarketRepository(session),
        candle_repository=CandleRepository(session),
        state_manager=runtime.state_manager,
        slippage_bps=settings.paper_trading_slippage_bps,
        fee_bps=settings.paper_trading_fee_bps,
        staleness_threshold=timedelta(seconds=settings.paper_trading_stale_price_threshold_seconds),
    )
