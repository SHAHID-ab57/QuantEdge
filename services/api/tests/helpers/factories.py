"""Factories for seeding database-backed test data.

All factories write through a provided session factory and commit, so they
compose cleanly with the shared ``session_factory`` fixture.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Candle, Exchange, Market

SessionFactory = async_sessionmaker[AsyncSession]


async def create_exchange(
    session_factory: SessionFactory,
    *,
    name: str = "Delta Exchange",
    slug: str = "delta",
    country: str = "India",
) -> UUID:
    """Insert an exchange and return its id."""
    async with session_factory() as session:
        exchange = Exchange(name=name, slug=slug, country=country)
        session.add(exchange)
        await session.commit()
        return exchange.id


async def create_market(
    session_factory: SessionFactory,
    *,
    exchange_id: UUID,
    symbol: str = "ETHUSD",
    base_asset: str = "ETH",
    quote_asset: str = "USD",
    market_type: str = "perpetual",
) -> UUID:
    """Insert a market under an existing exchange and return its id."""
    async with session_factory() as session:
        market = Market(
            exchange_id=exchange_id,
            symbol=symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            market_type=market_type,
        )
        session.add(market)
        await session.commit()
        return market.id


async def create_candles(
    session_factory: SessionFactory,
    market_id: UUID,
    rows: list[dict],
    *,
    timeframe: str = "1h",
) -> int:
    """Insert candle rows for a market and return the number inserted."""
    async with session_factory() as session:
        for row in rows:
            session.add(
                Candle(
                    market_id=market_id,
                    timeframe=row.get("timeframe", timeframe),
                    open_time=row["open_time"],
                    close_time=row["close_time"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    quote_volume=row.get("quote_volume"),
                    trade_count=row.get("trade_count"),
                    source=row.get("source", "delta"),
                )
            )
        await session.commit()
    return len(rows)


async def seed_market_with_candles(
    session_factory: SessionFactory,
    rows: list[dict],
    *,
    symbol: str = "ETHUSD",
) -> UUID:
    """Create an exchange + market and populate it with candle rows."""
    exchange_id = await create_exchange(session_factory)
    market_id = await create_market(session_factory, exchange_id=exchange_id, symbol=symbol)
    await create_candles(session_factory, market_id, rows)
    return market_id


def as_decimal(value: float | str | Decimal) -> Decimal:
    """Coerce a value to Decimal."""
    return Decimal(str(value))
