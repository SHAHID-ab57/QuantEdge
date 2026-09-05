"""Paper Trading service — place a market order against a real, realistic
fill, and track an account's positions and PnL.

Composes `MarketRepository`/`CandleRepository` directly (never a second
copy of them) and reads live state from the process-wide `MarketStateManager`
(`app/runtime.py`) — the same real market data every other live feature on
this platform already reads from, never a second data path invented for
this one.

**Accounting model, stated plainly** (see `PaperAccount`'s own docstring
for the schema side of this):

- `average_entry_price` (on `PaperPosition`) is the VWAP of *fill* prices
  only (post-slippage, pre-fee) — fees are never blended into cost basis.
- A **buy** immediately realizes its own fee as a certain, already-paid
  cost: `realized_pnl -= fee_applied`. It does not otherwise realize any
  gain/loss — converting cash into a position at cost is not a gain or a
  loss until that position is later sold.
- A **sell** realizes `(fill_price - average_entry_price) * quantity -
  fee_applied` — the price-move gain/loss on the quantity actually sold,
  net of this trade's own fee. `average_entry_price` itself never changes
  on a sell (it only ever moves via a buy's own VWAP average).
- **Once every position an account has ever held is fully closed, `balance`
  exactly equals `starting_balance + realized_pnl`** — every dollar has
  either been spent-then-recovered through a sell (netting into a realized
  gain/loss) or never spent at all. While a position is still open, the
  two numbers don't (and shouldn't) reconcile: the difference is exactly
  the cost-basis value of what's still held, which is neither a gain nor
  a loss yet — that's what `unrealized_pnl` is for, computed fresh on
  every read against a live price, never stored.

**Pre-trade risk limits, stated plainly:**

- **Halted check** (first, before anything else): a halted account rejects
  every order outright until an explicit `resume_trading` call — see that
  method's own docstring for why it also resets `peak_balance` to the
  account's current balance.
- **Position sizing**: this order's *resulting* quantity in its own symbol,
  valued at the *current* resolved quote (never the price a position was
  originally opened at), must not exceed `max_position_size_pct` of the
  account's *current* balance.
- **Exposure**: every other open position's *current* value (the same
  live-price-with-fallback lookup `list_positions` already uses) plus this
  order's own resulting value must not exceed `max_exposure_pct` of the
  account's *current* balance.
- **Drawdown/halt**, evaluated *after* the trade completes, never before:
  `peak_balance` only ever rises (`max(peak_balance, new_balance)`); if the
  new balance has fallen more than `max_drawdown_pct` below the (possibly
  just-raised) peak, `trading_halted` is set. This can only ever flip
  `False -> True` here — a halted account never reaches this check again
  until it's resumed (the halted check above rejects it first).

**Concurrency**: the whole read-check-write sequence above is guarded by
`PaperAccountRepository.try_apply_trade_effects`, an atomic
`UPDATE ... WHERE balance = :expected AND trading_halted = :expected` —
the same core primitive `TrainingJobRepository.try_transition_to_running`
uses for its own check-then-act race, adapted into a bounded
retry-and-recompute loop because what this feature needs to guard
(current balance, current prices, every other open position) can't be
pinned to one fixed status value the way a training job's `'pending'`
can. See `place_order`'s own docstring for the full mechanics.

**Stop-loss / take-profit, stated plainly** (see
`app.paper_trading.monitor.StopLossTakeProfitMonitor` for the
event-driven side of this): a long position's `stop_loss_price` must sit
below the current price and `take_profit_price` above it — either would
trigger the instant it was set otherwise — and, whenever both are
present, `stop_loss_price` must be strictly below `take_profit_price` too
(`_validate_thresholds`), which is what keeps the two trigger conditions
(`price <= stop_loss_price`, `price >= take_profit_price`) mutually
exclusive for every possible price, closing the "one tick crosses both"
question by construction rather than a runtime tie-break — see
`StopLossTakeProfitMonitor`'s own docstring for the deterministic
check-order it still keeps as defense-in-depth regardless. A triggered
close (`trigger_close`) reuses the *same* `apply_fill_model` and the
*same* `try_apply_trade_effects` atomic guard `place_order` uses — so a
triggered auto-close racing a concurrent manual close of the same
position can never both succeed, exactly like the exposure-limit race
above, just applied to `PaperPosition.quantity` instead of
`PaperAccount.balance`/`trading_halted`. The one deliberate difference:
`trigger_close` always closes *whatever is currently held*, re-read
fresh on every retry, never a fixed amount decided once — so if a
concurrent manual sell partially (not fully) closes the position first,
the trigger still closes the real remainder, not a stale, too-large
number. It also fills at a *wider* slippage
(`paper_trading_triggered_slippage_bps`, default wider than
`paper_trading_slippage_bps`) — a triggered exit during a fast price move
is not a perfect fill either; pretending otherwise would be exactly the
dishonest simulation this feature's realistic-execution guarantee exists
to avoid.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.paper_trading import PaperAccount, PaperOrder
from app.paper_trading.base import FillQuote
from app.paper_trading.errors import (
    AccountUpdateConflictError,
    InsufficientBalanceError,
    InsufficientPositionError,
    InvalidPaperOrderSortError,
    InvalidStopLossPriceError,
    InvalidTakeProfitPriceError,
    MaxExposureExceededError,
    MaxPositionSizeExceededError,
    PaperAccountNotFoundError,
    PositionNotFoundError,
    StopLossNotBelowTakeProfitError,
    TradingHaltedError,
)
from app.paper_trading.pricing import apply_fill_model, resolve_current_price
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    ORDER_SORT_COLUMNS,
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperAccountListResponse,
    PaperAccountResponse,
    PaperOrderListResponse,
    PaperOrderRequest,
    PaperOrderResponse,
    PaperPositionDTO,
    PaperPositionListResponse,
    PortfolioSummaryResponse,
    PositionThresholdsUpdateRequest,
    RiskSummaryResponse,
)
from app.services.market_query import MarketNotFoundError
from app.state.manager import MarketStateManager

#: A nonzero exposure/position value against an exactly-zero balance (a
#: fully cash-out account, legitimately reachable without ever going
#: negative) has no finite "% of balance" — reported as this large, fixed
#: sentinel rather than raising `ZeroDivisionError`, since it's always
#: unambiguously over any limit that could ever be configured (<= 100%).
_ZERO_BALANCE_SENTINEL_PCT = Decimal("999999")


class PaperTradingService:
    """The one entry point routers use for every paper trading operation."""

    def __init__(
        self,
        account_repository: PaperAccountRepository,
        order_repository: PaperOrderRepository,
        position_repository: PaperPositionRepository,
        market_repository: MarketRepository,
        candle_repository: CandleRepository,
        state_manager: MarketStateManager,
        slippage_bps: int,
        fee_bps: int,
        triggered_slippage_bps: int,
        staleness_threshold: timedelta,
        default_max_position_size_pct: Decimal,
        default_max_exposure_pct: Decimal,
        default_max_drawdown_pct: Decimal,
        max_order_attempts: int,
    ) -> None:
        self.account_repository = account_repository
        self.order_repository = order_repository
        self.position_repository = position_repository
        self.market_repository = market_repository
        self.candle_repository = candle_repository
        self.state_manager = state_manager
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        self.triggered_slippage_bps = triggered_slippage_bps
        self.staleness_threshold = staleness_threshold
        self.default_max_position_size_pct = default_max_position_size_pct
        self.default_max_exposure_pct = default_max_exposure_pct
        self.default_max_drawdown_pct = default_max_drawdown_pct
        self.max_order_attempts = max_order_attempts

    async def create_account(self, request: PaperAccountCreateRequest) -> PaperAccountResponse:
        account = PaperAccount(
            name=request.name,
            starting_balance=request.starting_balance,
            balance=request.starting_balance,
            realized_pnl=Decimal(0),
            max_position_size_pct=(
                request.max_position_size_pct
                if request.max_position_size_pct is not None
                else self.default_max_position_size_pct
            ),
            max_exposure_pct=(
                request.max_exposure_pct
                if request.max_exposure_pct is not None
                else self.default_max_exposure_pct
            ),
            max_drawdown_pct=(
                request.max_drawdown_pct
                if request.max_drawdown_pct is not None
                else self.default_max_drawdown_pct
            ),
            peak_balance=request.starting_balance,
            trading_halted=False,
        )
        created = await self.account_repository.create(account)
        return PaperAccountResponse.from_model(created)

    async def get_account(self, account_id: uuid.UUID) -> PaperAccountResponse:
        account = await self._get_account_or_404(account_id)
        return PaperAccountResponse.from_model(account)

    async def list_accounts(self, *, limit: int, offset: int) -> PaperAccountListResponse:
        accounts, total = await self.account_repository.list_all(limit=limit, offset=offset)
        return PaperAccountListResponse(
            accounts=[PaperAccountResponse.from_model(a) for a in accounts],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def place_order(
        self, account_id: uuid.UUID, request: PaperOrderRequest
    ) -> PaperOrderResponse:
        """Fill one market order immediately, completely, and realistically
        — guarded by pre-trade risk checks (halted, then position sizing,
        then exposure), with a drawdown/halt check applied after the fill.

        There is no pending/partial-fill state: every order either fills
        in full right now (long-only — a buy adds to a position, a sell
        reduces one) or is rejected outright (insufficient cash for a buy,
        insufficient held quantity for a sell, or a breached risk limit —
        never partially executed).

        **Concurrency.** Each attempt re-reads the account fresh, resolves
        a live price, re-evaluates every check, and finishes with a single
        atomic `UPDATE ... WHERE balance = :expected AND trading_halted =
        :expected` (`PaperAccountRepository.try_apply_trade_effects`). That
        `UPDATE` only ever matches if nothing else has touched this
        account since this attempt's own read — exactly the guarantee
        `TrainingJobRepository.try_transition_to_running` gives its own
        duplicate-run race, just expressed as "the row is still what I
        last read" instead of "the row is still `'pending'`", because this
        feature's precondition depends on live prices and every other open
        position, not one fixed column. When it doesn't match (another
        order — or a resume — committed first), this attempt has *not*
        touched the position table yet, so nothing needs to be undone: it
        simply loops, re-reads the now-current account and positions, and
        recomputes every check from scratch — meaning two orders that
        would jointly breach a limit can never both succeed, because the
        second is re-evaluated against the first's already-committed
        effect, not the stale numbers it started with. Bounded at
        `max_order_attempts` (default 5) so a request is never left to
        loop forever; exhausting it raises `AccountUpdateConflictError`,
        practically unreachable by a real two-way race (one retry is
        always enough) but never assumed away.
        """
        market = await self.market_repository.get_by_symbol(request.symbol)
        if market is None:
            raise MarketNotFoundError(request.symbol)

        for _attempt in range(self.max_order_attempts):
            account = await self._get_account_or_404(account_id)

            if account.trading_halted:
                raise TradingHaltedError(
                    account.balance, account.peak_balance, account.max_drawdown_pct
                )

            quote = await resolve_current_price(
                state_manager=self.state_manager,
                candle_repository=self.candle_repository,
                market_id=market.id,
                symbol=request.symbol,
                staleness_threshold=self.staleness_threshold,
            )
            fill = apply_fill_model(
                quote,
                side=request.side,
                quantity=request.quantity,
                slippage_bps=self.slippage_bps,
                fee_bps=self.fee_bps,
            )

            position = await self.position_repository.get_by_account_and_symbol(
                account_id, request.symbol
            )
            held = Decimal(position.quantity) if position is not None else Decimal(0)
            balance = Decimal(account.balance)

            realized_pnl_this_order: Decimal | None = None
            effective_stop_loss_price: Decimal | None = None
            effective_take_profit_price: Decimal | None = None
            if request.side == "buy":
                total_cost = fill.notional + fill.fee_applied
                if balance < total_cost:
                    raise InsufficientBalanceError(total_cost, balance)
                new_balance = balance - total_cost
                new_realized_pnl = Decimal(account.realized_pnl) - fill.fee_applied
                resulting_quantity = held + request.quantity

                thresholds_provided = (
                    request.stop_loss_price is not None or request.take_profit_price is not None
                )
                if thresholds_provided:
                    existing_stop_loss = (
                        Decimal(position.stop_loss_price)
                        if position is not None and position.stop_loss_price is not None
                        else None
                    )
                    existing_take_profit = (
                        Decimal(position.take_profit_price)
                        if position is not None and position.take_profit_price is not None
                        else None
                    )
                    # Merge: a value named in *this* request overrides; a
                    # field this request doesn't mention keeps whatever
                    # the position already had (never silently cleared by
                    # an order that never mentioned it). The cross-check
                    # (stop_loss < take_profit) always runs on the final,
                    # merged pair — but the vs-current-price check only
                    # applies to whichever field *this* request actually
                    # names, so an untouched, already-valid threshold is
                    # never re-rejected just because the price has since
                    # moved past it.
                    effective_stop_loss_price = (
                        request.stop_loss_price
                        if request.stop_loss_price is not None
                        else existing_stop_loss
                    )
                    effective_take_profit_price = (
                        request.take_profit_price
                        if request.take_profit_price is not None
                        else existing_take_profit
                    )
                    self._validate_thresholds(
                        current_price=quote.price,
                        stop_loss_price=effective_stop_loss_price,
                        take_profit_price=effective_take_profit_price,
                        check_stop_loss_against_current_price=request.stop_loss_price is not None,
                        check_take_profit_against_current_price=request.take_profit_price
                        is not None,
                    )
            else:
                if position is None or request.quantity > held:
                    raise InsufficientPositionError(request.symbol, request.quantity, held)
                realized_pnl_this_order = (
                    fill.fill_price - Decimal(position.average_entry_price)
                ) * request.quantity - fill.fee_applied
                net_proceeds = fill.notional - fill.fee_applied
                new_balance = balance + net_proceeds
                new_realized_pnl = Decimal(account.realized_pnl) + realized_pnl_this_order
                resulting_quantity = held - request.quantity

            # --- Pre-trade risk checks: current price, current balance ---
            resulting_position_value = resulting_quantity * quote.price
            resulting_position_pct = self._percentage_of_balance(resulting_position_value, balance)
            max_position_pct = Decimal(account.max_position_size_pct)
            if resulting_position_pct > max_position_pct:
                raise MaxPositionSizeExceededError(
                    request.symbol,
                    resulting_position_value,
                    balance,
                    resulting_position_pct,
                    max_position_pct,
                )

            other_exposure = await self._total_exposure_value(
                account_id, exclude_symbol=request.symbol
            )
            resulting_exposure = other_exposure + resulting_position_value
            resulting_exposure_pct = self._percentage_of_balance(resulting_exposure, balance)
            max_exposure_pct = Decimal(account.max_exposure_pct)
            if resulting_exposure_pct > max_exposure_pct:
                raise MaxExposureExceededError(
                    resulting_exposure, balance, resulting_exposure_pct, max_exposure_pct
                )

            new_peak_balance, new_trading_halted = self._apply_drawdown_tracking(
                account, new_balance
            )

            updated_account = await self.account_repository.try_apply_trade_effects(
                account_id,
                expected_balance=account.balance,
                expected_trading_halted=account.trading_halted,
                new_balance=new_balance,
                new_realized_pnl=new_realized_pnl,
                new_peak_balance=new_peak_balance,
                new_trading_halted=new_trading_halted,
            )
            if updated_account is None:
                continue  # lost the race — re-read and retry against fresh numbers

            if request.side == "buy":
                await self.position_repository.apply_buy(
                    account_id,
                    request.symbol,
                    request.quantity,
                    fill.fill_price,
                    stop_loss_price=effective_stop_loss_price,
                    take_profit_price=effective_take_profit_price,
                    thresholds_provided=(
                        request.stop_loss_price is not None or request.take_profit_price is not None
                    ),
                )
            else:
                await self.position_repository.apply_sell(position, request.quantity)

            order = PaperOrder(
                account_id=account_id,
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                raw_price=quote.price,
                fill_price=fill.fill_price,
                fill_time=datetime.now(UTC),
                price_source=quote.source,
                price_observed_at=quote.observed_at,
                is_stale_price=quote.is_stale,
                slippage_applied=fill.slippage_applied,
                fee_applied=fill.fee_applied,
                notional=fill.notional,
                realized_pnl=realized_pnl_this_order,
            )
            created = await self.order_repository.create(order)
            return PaperOrderResponse.from_model(created)

        raise AccountUpdateConflictError(self.max_order_attempts)

    async def trigger_close(
        self,
        account_id: uuid.UUID,
        symbol: str,
        *,
        reason: str,
        quote: FillQuote,
    ) -> PaperOrderResponse | None:
        """Close `symbol` entirely for this account, market-triggered by a
        crossed stop-loss/take-profit threshold — called only by
        `app.paper_trading.monitor.StopLossTakeProfitMonitor`, never a
        router (there is no HTTP caller to report a rejection to, so this
        never raises; it returns `None` when there is nothing to do).

        Reuses `apply_fill_model` and `PaperAccountRepository
        .try_apply_trade_effects` — the exact same fill model and atomic
        concurrency guard `place_order` uses — but is otherwise its own,
        smaller loop rather than a shared code path with `place_order`,
        for one deliberate reason: this always sells *whatever is
        currently held*, re-read fresh on every retry attempt, not a
        fixed quantity decided once. That matters for the concurrency
        guarantee this method exists to provide — if a concurrent manual
        sell partially (not fully) closes the position before this
        attempt's retry, the trigger adapts and closes the real
        remainder rather than failing on a now-stale, too-large number.
        `place_order`'s fixed, user-specified quantity is the right
        contract for a manual order; it would be the wrong one here.

        Position-sizing/exposure are not checked: a full close only ever
        *reduces* both, so they can never be breached by this. A halted
        account accepts no orders, including a triggered exit — halting
        is meant to stop trading entirely, not just new risk-taking.
        """
        market = await self.market_repository.get_by_symbol(symbol)
        if market is None:
            return None

        for _attempt in range(self.max_order_attempts):
            account = await self._get_account_or_404(account_id)
            if account.trading_halted:
                return None

            position = await self.position_repository.get_by_account_and_symbol(account_id, symbol)
            held = Decimal(position.quantity) if position is not None else Decimal(0)
            if held <= 0 or position is None:
                return None  # already closed — e.g. a concurrent manual close won

            balance = Decimal(account.balance)
            fill = apply_fill_model(
                quote,
                side="sell",
                quantity=held,
                slippage_bps=self.triggered_slippage_bps,
                fee_bps=self.fee_bps,
            )
            realized_pnl_this_order = (
                fill.fill_price - Decimal(position.average_entry_price)
            ) * held - fill.fee_applied
            net_proceeds = fill.notional - fill.fee_applied
            new_balance = balance + net_proceeds
            new_realized_pnl = Decimal(account.realized_pnl) + realized_pnl_this_order

            new_peak_balance, new_trading_halted = self._apply_drawdown_tracking(
                account, new_balance
            )

            updated_account = await self.account_repository.try_apply_trade_effects(
                account_id,
                expected_balance=account.balance,
                expected_trading_halted=account.trading_halted,
                new_balance=new_balance,
                new_realized_pnl=new_realized_pnl,
                new_peak_balance=new_peak_balance,
                new_trading_halted=new_trading_halted,
            )
            if updated_account is None:
                continue  # lost the race — re-read the (possibly now-smaller) position and retry

            await self.position_repository.apply_sell(position, held)

            order = PaperOrder(
                account_id=account_id,
                symbol=symbol,
                side="sell",
                quantity=held,
                raw_price=quote.price,
                fill_price=fill.fill_price,
                fill_time=datetime.now(UTC),
                price_source=quote.source,
                price_observed_at=quote.observed_at,
                is_stale_price=quote.is_stale,
                slippage_applied=fill.slippage_applied,
                fee_applied=fill.fee_applied,
                notional=fill.notional,
                realized_pnl=realized_pnl_this_order,
                trigger_reason=reason,
            )
            created = await self.order_repository.create(order)
            return PaperOrderResponse.from_model(created)

        return None  # retries exhausted — the next price tick gives this another chance

    async def update_position_thresholds(
        self, account_id: uuid.UUID, symbol: str, request: PositionThresholdsUpdateRequest
    ) -> PaperPositionDTO:
        """Set, update, or clear a position's stop-loss/take-profit.

        Only fields the request actually names (`model_fields_set`) are
        changed; an omitted field keeps the position's existing value.
        The cross-check (stop-loss below take-profit) always runs on the
        *final*, merged pair, so a newly-set stop-loss can't be left
        un-checked against an untouched, already-set take-profit — but
        the vs-current-price check only applies to whichever field this
        request actually names, so an untouched, already-valid threshold
        is never re-rejected just because the price has since moved.
        """
        await self._get_account_or_404(account_id)
        position = await self.position_repository.get_by_account_and_symbol(account_id, symbol)
        if position is None or Decimal(position.quantity) <= 0:
            raise PositionNotFoundError(account_id, symbol)

        quote = await self._current_price_for_symbol(symbol)
        if quote is None:
            raise MarketNotFoundError(symbol)

        fields = request.model_dump(exclude_unset=True)
        raw_stop_loss_price = fields.get("stop_loss_price", position.stop_loss_price)
        raw_take_profit_price = fields.get("take_profit_price", position.take_profit_price)
        new_stop_loss_price = (
            Decimal(raw_stop_loss_price) if raw_stop_loss_price is not None else None
        )
        new_take_profit_price = (
            Decimal(raw_take_profit_price) if raw_take_profit_price is not None else None
        )
        self._validate_thresholds(
            current_price=quote.price,
            stop_loss_price=new_stop_loss_price,
            take_profit_price=new_take_profit_price,
            check_stop_loss_against_current_price="stop_loss_price" in fields,
            check_take_profit_against_current_price="take_profit_price" in fields,
        )

        updated = await self.position_repository.update(
            position,
            {"stop_loss_price": new_stop_loss_price, "take_profit_price": new_take_profit_price},
        )
        return PaperPositionDTO.from_model(
            updated, current_price=quote.price, price_source=quote.source
        )

    async def resume_trading(self, account_id: uuid.UUID) -> PaperAccountResponse:
        """Explicitly clear a drawdown halt — the *only* way it ever
        clears (this feature's own spec: no self-healing on balance
        recovery — nothing about *this* trade or any later one ever
        clears `trading_halted` on its own; only this explicit call does).

        `peak_balance` is reset to the account's current balance as part
        of the same action. Without that, an account resumed while still
        deep in drawdown against its old, untouched peak would measure
        straight back below the same threshold and re-halt after its
        very next order — regardless of that order's own direction or
        size — making "resume" nearly indistinguishable from "allow
        exactly one more order." Resetting the high-water mark to *now*
        is what a manual risk override conventionally means: the account
        starts being measured fresh from the point someone explicitly
        vouched for it, not from a peak that trade already lost.
        """
        account = await self._get_account_or_404(account_id)
        updated = await self.account_repository.update(
            account, {"trading_halted": False, "peak_balance": account.balance}
        )
        return PaperAccountResponse.from_model(updated)

    async def risk_summary(self, account_id: uuid.UUID) -> RiskSummaryResponse:
        """This account's own current exposure and drawdown against its
        configured limits, and whether trading is halted — computed fresh
        against live prices on every read, exactly like `summary`'s own
        `unrealized_pnl`, never stored."""
        account = await self._get_account_or_404(account_id)
        balance = Decimal(account.balance)
        peak_balance = Decimal(account.peak_balance)

        total_exposure = await self._total_exposure_value(account_id)
        current_exposure_pct = self._percentage_of_balance(total_exposure, balance)
        current_drawdown_pct = (
            Decimal(0)
            if peak_balance == 0
            else ((peak_balance - balance) / peak_balance) * Decimal(100)
        )
        max_exposure_pct = Decimal(account.max_exposure_pct)
        max_drawdown_pct = Decimal(account.max_drawdown_pct)

        return RiskSummaryResponse(
            account_id=str(account.id),
            balance=balance,
            peak_balance=peak_balance,
            current_exposure_pct=current_exposure_pct,
            max_exposure_pct=max_exposure_pct,
            exposure_headroom_pct=max_exposure_pct - current_exposure_pct,
            current_drawdown_pct=current_drawdown_pct,
            max_drawdown_pct=max_drawdown_pct,
            drawdown_headroom_pct=max_drawdown_pct - current_drawdown_pct,
            max_position_size_pct=Decimal(account.max_position_size_pct),
            trading_halted=account.trading_halted,
        )

    async def list_orders(
        self,
        account_id: uuid.UUID,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> PaperOrderListResponse:
        await self._get_account_or_404(account_id)
        if sort not in ORDER_SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidPaperOrderSortError(sort, direction, tuple(ORDER_SORT_COLUMNS))
        orders, total = await self.order_repository.search(
            account_id=account_id, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return PaperOrderListResponse(
            orders=[PaperOrderResponse.from_model(o) for o in orders],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_positions(self, account_id: uuid.UUID) -> PaperPositionListResponse:
        """Every symbol this account currently holds, marked to the *same*
        live price a fill would use — never a slippage-adjusted
        hypothetical exit price (mark-to-market, not a projected trade)."""
        await self._get_account_or_404(account_id)
        positions = await self.position_repository.list_open(account_id)
        dtos = []
        for position in positions:
            quote = await self._current_price_for_symbol(position.symbol)
            if quote is None:
                continue
            dtos.append(
                PaperPositionDTO.from_model(
                    position, current_price=quote.price, price_source=quote.source
                )
            )
        return PaperPositionListResponse(positions=dtos)

    async def summary(self, account_id: uuid.UUID) -> PortfolioSummaryResponse:
        account = await self._get_account_or_404(account_id)
        positions = (await self.list_positions(account_id)).positions
        unrealized_pnl = sum((p.unrealized_pnl for p in positions), Decimal(0))
        position_value = sum((p.current_price * p.quantity for p in positions), Decimal(0))
        return PortfolioSummaryResponse(
            account_id=str(account.id),
            balance=account.balance,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_equity=Decimal(account.balance) + position_value,
            open_position_count=len(positions),
        )

    async def _get_account_or_404(self, account_id: uuid.UUID) -> PaperAccount:
        account = await self.account_repository.get_by_id(account_id)
        if account is None:
            raise PaperAccountNotFoundError(account_id)
        return account

    async def _current_price_for_symbol(self, symbol: str) -> FillQuote | None:
        """The live-price-with-fallback quote for `symbol` right now, or
        `None` if the market itself no longer exists — the same "skip a
        position whose market vanished" behavior `list_positions` already
        had, now shared with every other current-price consumer this
        task's risk checks added (`_total_exposure_value`)."""
        market = await self.market_repository.get_by_symbol(symbol)
        if market is None:
            return None
        return await resolve_current_price(
            state_manager=self.state_manager,
            candle_repository=self.candle_repository,
            market_id=market.id,
            symbol=symbol,
            staleness_threshold=self.staleness_threshold,
        )

    async def _total_exposure_value(
        self, account_id: uuid.UUID, *, exclude_symbol: str | None = None
    ) -> Decimal:
        """Every open position's *current* value (quantity × the same
        live-price-with-fallback quote a fill would use), summed —
        `exclude_symbol` lets `place_order` value the symbol it's about to
        trade using its own already-resolved quote and *resulting*
        quantity instead of the stored pre-trade one."""
        positions = await self.position_repository.list_open(account_id)
        total = Decimal(0)
        for position in positions:
            if position.symbol == exclude_symbol:
                continue
            quote = await self._current_price_for_symbol(position.symbol)
            if quote is None:
                continue
            total += Decimal(position.quantity) * quote.price
        return total

    @staticmethod
    def _percentage_of_balance(value: Decimal, balance: Decimal) -> Decimal:
        """`value` as a percentage of `balance` — `_ZERO_BALANCE_SENTINEL_PCT`
        (never a `ZeroDivisionError`) for the rare exact-zero-balance case."""
        if balance == 0:
            return Decimal(0) if value == 0 else _ZERO_BALANCE_SENTINEL_PCT
        return (value / balance) * Decimal(100)

    @staticmethod
    def _apply_drawdown_tracking(
        account: PaperAccount, new_balance: Decimal
    ) -> tuple[Decimal, bool]:
        """Peak-balance tracking and the drawdown halt, evaluated fresh
        after every balance-changing event (this feature's own spec).
        `peak_balance` only ever rises; `trading_halted` can only flip
        `False -> True` here, since a halted account is rejected before
        ever reaching this point again (see `place_order`) — never reset
        by this method itself (only `resume_trading` clears it)."""
        new_peak = max(Decimal(account.peak_balance), new_balance)
        threshold = new_peak * (Decimal(1) - Decimal(account.max_drawdown_pct) / Decimal(100))
        new_halted = new_balance < threshold
        return new_peak, new_halted

    @staticmethod
    def _validate_thresholds(
        *,
        current_price: Decimal,
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        check_stop_loss_against_current_price: bool,
        check_take_profit_against_current_price: bool,
    ) -> None:
        """A long position's stop-loss must sit below `current_price` and
        its take-profit above it — either would trigger the instant it's
        set otherwise. That check only applies to whichever of the two
        *this* call is actually setting
        (`check_stop_loss_against_current_price`/
        `check_take_profit_against_current_price` — false for a field
        merely carried over, unmentioned, from the position's existing
        value): an untouched, already-valid threshold must never be
        re-rejected just because the price has since moved past it — that
        would make an unrelated order (or an update to the *other*
        threshold) fail for a reason it never asked about.

        The cross-check is different: whenever both are present in the
        *final*, merged pair — touched or not — `stop_loss_price` must be
        strictly less than `take_profit_price`. Each was independently
        valid against its own current price at whatever moment it was
        set, but that alone doesn't stop a high stop-loss and a low
        take-profit being set at two different times as the price moved
        between them — this is what actually closes that gap, keeping
        `price <= stop_loss_price` and `price >= take_profit_price`
        mutually exclusive for every possible price. See
        `app.paper_trading.monitor`'s own docstring for why that's this
        feature's actual answer to "what if one tick crosses both."
        """
        if (
            check_stop_loss_against_current_price
            and stop_loss_price is not None
            and stop_loss_price >= current_price
        ):
            raise InvalidStopLossPriceError(stop_loss_price, current_price)
        if (
            check_take_profit_against_current_price
            and take_profit_price is not None
            and take_profit_price <= current_price
        ):
            raise InvalidTakeProfitPriceError(take_profit_price, current_price)
        if (
            stop_loss_price is not None
            and take_profit_price is not None
            and stop_loss_price >= take_profit_price
        ):
            raise StopLossNotBelowTakeProfitError(stop_loss_price, take_profit_price)
