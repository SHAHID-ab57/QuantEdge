"""Market data access repository.

All SQL for reading market metadata lives in this module.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market


class MarketRepository:
    """Database access for markets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> list[Market]:
        """Return all markets ordered by symbol."""
        query = select(Market).order_by(Market.symbol.asc())
        return list((await self._session.execute(query)).scalars())

    async def get_by_symbol(self, symbol: str) -> Market | None:
        """Return the market matching a symbol, or ``None``."""
        query = select(Market).where(Market.symbol == symbol)
        return (await self._session.execute(query)).scalar_one_or_none()