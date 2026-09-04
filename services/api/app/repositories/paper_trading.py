"""Paper Trading data access — accounts, their filled orders, and their
materialized open positions.

All SQL for this feature lives here; the service layer never builds
queries directly — the same repository/service split every other domain
on this platform already follows.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.paper_trading import PaperAccount, PaperOrder, PaperPosition

ORDER_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "symbol": PaperOrder.symbol,
    "side": PaperOrder.side,
    "fill_time": PaperOrder.fill_time,
    "created_at": PaperOrder.created_at,
}


class PaperAccountRepository:
    """Create/read/update access to paper trading accounts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, account: PaperAccount) -> PaperAccount:
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def get_by_id(self, account_id: uuid.UUID) -> PaperAccount | None:
        return await self.session.get(PaperAccount, account_id)

    async def list_all(self, *, limit: int, offset: int) -> tuple[list[PaperAccount], int]:
        """Every account, most recently created first — the frontend's
        "reopen my account" fallback, since nothing in this platform
        authenticates a user to key an account off of."""
        total = (
            await self.session.execute(select(func.count()).select_from(PaperAccount))
        ).scalar_one()
        result = await self.session.execute(
            select(PaperAccount)
            .order_by(PaperAccount.created_at.desc(), PaperAccount.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def update(self, account: PaperAccount, fields: dict[str, Any]) -> PaperAccount:
        for key, value in fields.items():
            setattr(account, key, value)
        await self.session.commit()
        await self.session.refresh(account)
        return account


class PaperOrderRepository:
    """Create/search access to filled paper orders."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, order: PaperOrder) -> PaperOrder:
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def search(
        self,
        *,
        account_id: uuid.UUID,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[PaperOrder], int]:
        """One page of an account's own order history, most recent first by default."""
        count_query = (
            select(func.count()).select_from(PaperOrder).where(PaperOrder.account_id == account_id)
        )
        total = (await self.session.execute(count_query)).scalar_one()

        column = ORDER_SORT_COLUMNS[sort]
        order = column.desc() if direction == "desc" else column.asc()
        query = (
            select(PaperOrder)
            .where(PaperOrder.account_id == account_id)
            .order_by(order, PaperOrder.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total


@dataclass
class PositionUpsertResult:
    """The position row after applying one order, plus what it was
    *before* — the service layer needs the prior `average_entry_price` to
    compute a sell's own realized PnL, and re-deriving it from the
    already-mutated row would be wrong."""

    position: PaperPosition
    previous_quantity: Decimal
    previous_average_entry_price: Decimal


class PaperPositionRepository:
    """Materialized open-position access — updated in place by every
    order, never recomputed from `PaperOrder` history on read."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_account_and_symbol(
        self, account_id: uuid.UUID, symbol: str
    ) -> PaperPosition | None:
        result = await self.session.execute(
            select(PaperPosition).where(
                PaperPosition.account_id == account_id, PaperPosition.symbol == symbol
            )
        )
        return result.scalar_one_or_none()

    async def list_open(self, account_id: uuid.UUID) -> list[PaperPosition]:
        """Every symbol this account currently holds (`quantity > 0`) —
        a fully-closed position stays in the table at `quantity = 0`
        (see `PaperPosition`'s own docstring) but is never an "open
        position" a caller should see here."""
        result = await self.session.execute(
            select(PaperPosition)
            .where(PaperPosition.account_id == account_id, PaperPosition.quantity > 0)
            .order_by(PaperPosition.symbol.asc())
        )
        return list(result.scalars().all())

    async def apply_buy(
        self, account_id: uuid.UUID, symbol: str, quantity: Decimal, fill_price: Decimal
    ) -> PositionUpsertResult:
        """Add `quantity` at `fill_price` to this account's position in
        `symbol`, VWAP-averaging into any existing holding — creating the
        row on a symbol held for the first time."""
        position = await self.get_by_account_and_symbol(account_id, symbol)
        if position is None:
            previous_quantity = Decimal(0)
            previous_average = Decimal(0)
            position = PaperPosition(
                account_id=account_id,
                symbol=symbol,
                quantity=quantity,
                average_entry_price=fill_price,
            )
            self.session.add(position)
        else:
            previous_quantity = Decimal(position.quantity)
            previous_average = Decimal(position.average_entry_price)
            new_quantity = previous_quantity + quantity
            position.average_entry_price = (
                previous_quantity * previous_average + quantity * fill_price
            ) / new_quantity
            position.quantity = new_quantity
        await self.session.commit()
        await self.session.refresh(position)
        return PositionUpsertResult(position, previous_quantity, previous_average)

    async def apply_sell(self, position: PaperPosition, quantity: Decimal) -> PositionUpsertResult:
        """Reduce `position` by `quantity` — the caller (`PaperTradingService
        .place_order`) has already verified `quantity <= position.quantity`
        (no shorting); `average_entry_price` is left unchanged by a sell
        (it only ever moves via a *buy*'s own VWAP average)."""
        previous_quantity = Decimal(position.quantity)
        previous_average = Decimal(position.average_entry_price)
        position.quantity = previous_quantity - quantity
        await self.session.commit()
        await self.session.refresh(position)
        return PositionUpsertResult(position, previous_quantity, previous_average)
