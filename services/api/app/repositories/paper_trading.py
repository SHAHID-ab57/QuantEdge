"""Paper Trading data access — accounts, their filled orders, and their
materialized open positions.

All SQL for this feature lives here; the service layer never builds
queries directly — the same repository/service split every other domain
on this platform already follows.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.paper_trading import (
    PaperAccount,
    PaperFundingSettlement,
    PaperOrder,
    PaperPosition,
    PaperStrategyDecision,
)

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
        """Read the account fresh from the database, never from the session's
        identity map. `Session.get` returns an already-loaded instance without
        emitting SQL, and these sessions do not expire on commit, so a retry
        after a lost race would otherwise re-read the *stale* row (and its
        stale `state_version`), fail the guard again, and exhaust its
        attempts. The guard is only as good as the freshness of what it
        compares against."""
        return await self.session.get(PaperAccount, account_id, populate_existing=True)

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

    async def list_strategy_enabled(self) -> list[PaperAccount]:
        """Every account with its automated strategy currently turned on —
        `app.services.paper_trading_strategy.PaperTradingStrategyScheduler`'s
        own per-tick query. Read fresh at the start of every tick, never
        cached across ticks, so disabling an account's strategy always
        takes effect by the very next tick."""
        result = await self.session.execute(
            select(PaperAccount).where(PaperAccount.strategy_enabled.is_(True))
        )
        return list(result.scalars().all())

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
        expected_state_version: int,
        new_balance: Decimal,
        new_realized_pnl: Decimal,
        new_peak_balance: Decimal,
        new_trading_halted: bool,
        commit: bool = True,
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

        **`expected_state_version` is what makes this guard cover margin.**
        Comparing `balance` alone cannot see a change that leaves cash
        untouched: a liquidation forfeits a position's margin (cash
        returned: zero) and a funding payment taken from margin changes no
        cash either. Every guarded update therefore also bumps
        `state_version`, and the `WHERE` clause matches on it, so any two
        updates to the same account, whatever they touch, are serialized
        exactly as two balance changes always were.

        **`commit=False` makes the guard the first write of one transaction.**
        `PaperTradingService` runs the guarded `UPDATE` first, then writes the
        position and the order in the *same* transaction and commits once, so
        the account row lock the `UPDATE` takes is held until everything it
        gates has been written. Without that, a second actor could read the
        already-committed account (new version) but the not-yet-updated
        position, pass the guard on that stale read, and close a position that
        was already closed — a window real Postgres opens (found by running the
        liquidation-versus-manual-close race against it, which two sessions
        sharing one SQLite connection can never reproduce). When the guard
        loses, the transaction is simply ended: the guard must be the first
        write of it, so there is nothing else to undo.

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
                PaperAccount.state_version == expected_state_version,
            )
            .values(
                balance=new_balance,
                realized_pnl=new_realized_pnl,
                peak_balance=new_peak_balance,
                trading_halted=new_trading_halted,
                state_version=expected_state_version + 1,
            )
        )
        assert isinstance(result, CursorResult)
        if result.rowcount == 0:
            # Lost the race. The guard is the first write of its transaction,
            # so nothing else is pending: just end it. (Not a rollback: that
            # would expire every ORM object the caller still holds — the
            # market row it resolved before its retry loop — and a lazy
            # reload in async code raises `MissingGreenlet`.)
            await self.session.commit()
            return None
        if commit:
            await self.session.commit()
        # The core UPDATE bypasses the ORM, so re-read past any cached instance.
        return await self.session.get(PaperAccount, account_id, populate_existing=True)


class PaperOrderRepository:
    """Create/search access to filled paper orders."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, order: PaperOrder, *, commit: bool = True) -> PaperOrder:
        """Add `order`. With `commit=False` it is only flushed, so it joins the
        caller's still-open transaction (see `try_apply_trade_effects`)."""
        self.session.add(order)
        if commit:
            await self.session.commit()
            await self.session.refresh(order)
        else:
            await self.session.flush()
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


#: `(entry_price, quantity, margin) -> liquidation price or None`, supplied by
#: the service layer (which owns the maintenance-margin rate) so the
#: repository never needs to know it.
LiquidationPriceFn = Callable[[Decimal, Decimal, Decimal], Decimal | None]


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
        # `populate_existing`: a row already loaded in this session (the
        # monitor lists positions first, then re-reads each to act on it) must
        # be refreshed from the database, not served from the identity map,
        # or a position another session has just closed still looks open.
        result = await self.session.execute(
            select(PaperPosition)
            .where(PaperPosition.account_id == account_id, PaperPosition.symbol == symbol)
            .execution_options(populate_existing=True)
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
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def list_open_monitored(self, symbol: str) -> list[PaperPosition]:
        """Every open position (across *every* account) in `symbol` that
        the price monitor has anything to watch for: a stop-loss and/or
        take-profit, or a liquidation price (every short, and every
        leveraged long). `StopLossTakeProfitMonitor`'s own query, run once
        per relevant price event for that symbol."""
        result = await self.session.execute(
            select(PaperPosition).where(
                PaperPosition.symbol == symbol,
                PaperPosition.quantity > 0,
                or_(
                    PaperPosition.stop_loss_price.is_not(None),
                    PaperPosition.take_profit_price.is_not(None),
                    PaperPosition.liquidation_price.is_not(None),
                ),
            )
        )
        return list(result.scalars().all())

    async def list_open_for_symbols(self, symbols: list[str]) -> list[PaperPosition]:
        """Every open position, across every account, in any of `symbols`."""
        if not symbols:
            return []
        result = await self.session.execute(
            select(PaperPosition).where(
                PaperPosition.symbol.in_(symbols), PaperPosition.quantity > 0
            )
        )
        return list(result.scalars().all())

    async def list_open_symbols(self) -> list[str]:
        """The distinct symbols any account currently holds an open position in."""
        result = await self.session.execute(
            select(PaperPosition.symbol).where(PaperPosition.quantity > 0).distinct()
        )
        return sorted(result.scalars().all())

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

    async def apply_open(
        self,
        account_id: uuid.UUID,
        symbol: str,
        *,
        side: str,
        quantity: Decimal,
        fill_price: Decimal,
        leverage: Decimal,
        margin_added: Decimal,
        liquidation_price_for: "LiquidationPriceFn",
        opened_at: datetime,
        stop_loss_price: Decimal | None = None,
        take_profit_price: Decimal | None = None,
        thresholds_provided: bool = False,
        commit: bool = True,
    ) -> PositionUpsertResult:
        """Open, or add to, a position of `quantity` at `fill_price`,
        VWAP-averaging into any existing holding of the same side — creating
        the row on a symbol held for the first time, or re-opening a flat
        one. `margin_added` is the margin this order posts; the resulting
        liquidation price is recomputed from the *resulting* entry price,
        quantity and total margin (`liquidation_price_for`).

        `stop_loss_price`/`take_profit_price` are set on the position only
        when `thresholds_provided` is true (the caller — an order that
        explicitly named at least one of them — already validated both
        against the current price and each other); otherwise any existing
        thresholds on the position are left completely untouched, so an
        unrelated order that doesn't mention them can never silently clear a
        stop-loss someone set earlier.
        """
        position = await self.get_by_account_and_symbol(account_id, symbol)
        if position is None:
            previous_quantity = Decimal(0)
            previous_average = Decimal(0)
            new_margin = margin_added
            position = PaperPosition(
                account_id=account_id,
                symbol=symbol,
                side=side,
                leverage=leverage,
                margin=new_margin,
                quantity=quantity,
                average_entry_price=fill_price,
                liquidation_price=liquidation_price_for(fill_price, quantity, new_margin),
                opened_at=opened_at,
                stop_loss_price=stop_loss_price if thresholds_provided else None,
                take_profit_price=take_profit_price if thresholds_provided else None,
            )
            self.session.add(position)
        else:
            previous_quantity = Decimal(position.quantity)
            previous_average = Decimal(position.average_entry_price)
            if previous_quantity == 0:
                # A re-opened, previously-flat row: nothing carries over.
                new_quantity = quantity
                new_average = fill_price
                new_margin = margin_added
                position.opened_at = opened_at
            else:
                new_quantity = previous_quantity + quantity
                new_average = (
                    previous_quantity * previous_average + quantity * fill_price
                ) / new_quantity
                new_margin = Decimal(position.margin) + margin_added
            position.side = side
            position.leverage = leverage
            position.quantity = new_quantity
            position.average_entry_price = new_average
            position.margin = new_margin
            position.liquidation_price = liquidation_price_for(
                new_average, new_quantity, new_margin
            )
            if thresholds_provided:
                position.stop_loss_price = stop_loss_price
                position.take_profit_price = take_profit_price
        await self._persist(position, commit)
        return PositionUpsertResult(position, previous_quantity, previous_average)

    async def _persist(self, position: PaperPosition, commit: bool) -> None:
        """Commit (and reload) the position, or just flush it into the
        caller's still-open transaction when `commit` is false."""
        if commit:
            await self.session.commit()
            await self.session.refresh(position)
        else:
            await self.session.flush()

    async def apply_reduce(
        self,
        position: PaperPosition,
        quantity: Decimal,
        *,
        margin_released: Decimal,
        commit: bool = True,
    ) -> PositionUpsertResult:
        """Reduce `position` by `quantity`, releasing `margin_released` of
        its margin — the caller (`PaperTradingService.place_order`/
        `.trigger_close`) has already verified `quantity <=
        position.quantity` (an order that would flip through zero is
        rejected before it gets here). `average_entry_price` and `leverage`
        are left unchanged by a reduction, and because margin is released
        pro rata the liquidation price is unchanged too. Reaching exactly
        `0` also clears every threshold, the liquidation price and the
        margin — a flat position has nothing left to protect, and either
        threshold would be meaningless against whatever price a later
        re-open happens to fill at."""
        previous_quantity = Decimal(position.quantity)
        previous_average = Decimal(position.average_entry_price)
        position.quantity = previous_quantity - quantity
        if position.quantity == 0:
            position.stop_loss_price = None
            position.take_profit_price = None
            position.liquidation_price = None
            position.margin = Decimal(0)
        else:
            position.margin = Decimal(position.margin) - margin_released
        await self._persist(position, commit)
        return PositionUpsertResult(position, previous_quantity, previous_average)

    async def apply_margin_change(
        self,
        position: PaperPosition,
        *,
        margin: Decimal,
        liquidation_price: Decimal | None,
        commit: bool = True,
    ) -> PaperPosition:
        """Set a position's margin and liquidation price — used when a
        funding payment the account's cash could not cover is taken from
        the position's own margin (which moves its liquidation price)."""
        position.margin = margin
        position.liquidation_price = liquidation_price
        await self._persist(position, commit)
        return position


class PaperFundingSettlementRepository:
    """Create/lookup access to funding settlements, the idempotency record
    for `app.services.paper_funding`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, account_id: uuid.UUID, symbol: str, funding_time: datetime) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(PaperFundingSettlement)
            .where(
                PaperFundingSettlement.account_id == account_id,
                PaperFundingSettlement.symbol == symbol,
                PaperFundingSettlement.funding_time == funding_time,
            )
        )
        return result.scalar_one() > 0

    async def create(
        self, settlement: PaperFundingSettlement, *, commit: bool = True
    ) -> PaperFundingSettlement:
        self.session.add(settlement)
        if commit:
            await self.session.commit()
            await self.session.refresh(settlement)
        else:
            await self.session.flush()
        return settlement

    async def list_for_account(
        self, account_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[PaperFundingSettlement], int]:
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(PaperFundingSettlement)
                .where(PaperFundingSettlement.account_id == account_id)
            )
        ).scalar_one()
        result = await self.session.execute(
            select(PaperFundingSettlement)
            .where(PaperFundingSettlement.account_id == account_id)
            .order_by(PaperFundingSettlement.funding_time.desc(), PaperFundingSettlement.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total


class PaperStrategyDecisionRepository:
    """Create/list access to the automated strategy's own decision log —
    one row per strategy-enabled account per scheduler tick, acted on or
    not (see `PaperStrategyDecision`'s own docstring)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, decision: PaperStrategyDecision) -> PaperStrategyDecision:
        self.session.add(decision)
        await self.session.commit()
        await self.session.refresh(decision)
        return decision

    async def list_for_account(
        self, account_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[PaperStrategyDecision], int]:
        """One page of an account's own decision log, most recent first —
        the Strategy panel's decision log data source."""
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(PaperStrategyDecision)
                .where(PaperStrategyDecision.account_id == account_id)
            )
        ).scalar_one()
        result = await self.session.execute(
            select(PaperStrategyDecision)
            .where(PaperStrategyDecision.account_id == account_id)
            .order_by(PaperStrategyDecision.created_at.desc(), PaperStrategyDecision.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total
