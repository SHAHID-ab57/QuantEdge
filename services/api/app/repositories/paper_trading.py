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

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
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

    async def try_apply_trade_effects(
        self,
        account_id: uuid.UUID,
        *,
        expected_balance: Decimal,
        expected_trading_halted: bool,
        new_balance: Decimal,
        new_realized_pnl: Decimal,
        new_peak_balance: Decimal,
        new_trading_halted: bool,
    ) -> PaperAccount | None:
        """Atomically apply one order's balance/realized-PnL/peak-balance/
        halt effects, or fail closed if the account changed since the
        caller last read it.

        The same core primitive `TrainingJobRepository
        .try_transition_to_running` uses — a single `UPDATE ... WHERE`
        whose matched-row-count tells the caller whether its precondition
        still held — adapted here because the precondition this feature
        needs to guard (the account's current balance and halt state,
        which `PaperTradingService.place_order` used to compute this
        order's fill, position-sizing check, and exposure check) can't be
        pinned to one fixed status value the way a training job's
        `'pending'` can: it's whatever the caller most recently read, and
        those checks themselves depend on live prices and every other open
        position, not just this row.

        Two concurrent orders against the same account can never both
        still match an unmodified row: Postgres serializes the two
        `UPDATE`s (same primary key), so whichever commits first changes
        `balance`, and the second's `WHERE` clause matches zero rows.
        Returns `None` in that case — the caller
        (`PaperTradingService.place_order`) treats that as "re-read the
        account and its positions, recompute every check against the
        fresh live numbers, and retry," never as "proceed anyway," so a
        losing order is re-evaluated against the *other* order's
        now-committed effect rather than silently allowed to stack past a
        limit it would have breached alone.
        """
        result = await self.session.execute(
            update(PaperAccount)
            .where(
                PaperAccount.id == account_id,
                PaperAccount.balance == expected_balance,
                PaperAccount.trading_halted == expected_trading_halted,
            )
            .values(
                balance=new_balance,
                realized_pnl=new_realized_pnl,
                peak_balance=new_peak_balance,
                trading_halted=new_trading_halted,
            )
        )
        await self.session.commit()
        assert isinstance(result, CursorResult)
        if result.rowcount == 0:
            return None
        return await self.get_by_id(account_id)


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

    async def list_open_with_thresholds(self, symbol: str) -> list[PaperPosition]:
        """Every open position (across *every* account) in `symbol` that
        has a stop-loss and/or take-profit set — `StopLossTakeProfitMonitor`'s
        own query, run once per relevant price event for that symbol."""
        result = await self.session.execute(
            select(PaperPosition).where(
                PaperPosition.symbol == symbol,
                PaperPosition.quantity > 0,
                or_(
                    PaperPosition.stop_loss_price.is_not(None),
                    PaperPosition.take_profit_price.is_not(None),
                ),
            )
        )
        return list(result.scalars().all())

    async def update(self, position: PaperPosition, fields: dict[str, Any]) -> PaperPosition:
        """Apply a partial update — the same "every key applied
        unconditionally, including an explicit `None`" contract
        `PaperAccountRepository.update` uses, so an explicit `None` here
        clears a threshold rather than being mistaken for "leave it
        unchanged" (the caller — `PaperTradingService
        .update_position_thresholds` — has already distinguished
        "omitted" from "explicitly null" before calling this)."""
        for key, value in fields.items():
            setattr(position, key, value)
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def apply_buy(
        self,
        account_id: uuid.UUID,
        symbol: str,
        quantity: Decimal,
        fill_price: Decimal,
        *,
        stop_loss_price: Decimal | None = None,
        take_profit_price: Decimal | None = None,
        thresholds_provided: bool = False,
    ) -> PositionUpsertResult:
        """Add `quantity` at `fill_price` to this account's position in
        `symbol`, VWAP-averaging into any existing holding — creating the
        row on a symbol held for the first time.

        `stop_loss_price`/`take_profit_price` are set on the position
        only when `thresholds_provided` is true (the caller — an order
        that explicitly named at least one of them — already validated
        both against the current price and each other); otherwise any
        existing thresholds on the position are left completely
        untouched, so an unrelated buy that doesn't mention them can
        never silently clear a stop-loss someone set earlier.
        """
        position = await self.get_by_account_and_symbol(account_id, symbol)
        if position is None:
            previous_quantity = Decimal(0)
            previous_average = Decimal(0)
            position = PaperPosition(
                account_id=account_id,
                symbol=symbol,
                quantity=quantity,
                average_entry_price=fill_price,
                stop_loss_price=stop_loss_price if thresholds_provided else None,
                take_profit_price=take_profit_price if thresholds_provided else None,
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
            if thresholds_provided:
                position.stop_loss_price = stop_loss_price
                position.take_profit_price = take_profit_price
        await self.session.commit()
        await self.session.refresh(position)
        return PositionUpsertResult(position, previous_quantity, previous_average)

    async def apply_sell(self, position: PaperPosition, quantity: Decimal) -> PositionUpsertResult:
        """Reduce `position` by `quantity` — the caller (`PaperTradingService
        .place_order`/`.trigger_close`) has already verified `quantity <=
        position.quantity` (no shorting); `average_entry_price` is left
        unchanged by a sell (it only ever moves via a *buy*'s own VWAP
        average). Reaching exactly `0` also clears
        `stop_loss_price`/`take_profit_price` — a flat position has
        nothing left to protect, and either would be meaningless against
        whatever price a later re-buy happens to open at."""
        previous_quantity = Decimal(position.quantity)
        previous_average = Decimal(position.average_entry_price)
        position.quantity = previous_quantity - quantity
        if position.quantity == 0:
            position.stop_loss_price = None
            position.take_profit_price = None
        await self.session.commit()
        await self.session.refresh(position)
        return PositionUpsertResult(position, previous_quantity, previous_average)
