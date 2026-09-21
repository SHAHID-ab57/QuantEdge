"""Paper Trading service — place a market order against a real, realistic
fill, and track an account's positions and PnL.

Composes `MarketRepository`/`CandleRepository` directly (never a second
copy of them) and reads live state from the process-wide `MarketStateManager`
(`app/runtime.py`) — the same real market data every other live feature on
this platform already reads from, never a second data path invented for
this one.

**Accounting model, stated plainly** (see `PaperAccount`'s own docstring
for the schema side of this):

- A position is **long or short**, one net position per `(account, symbol)`,
  optionally **leveraged** with **isolated margin** (fixed when it opens).
  `PaperAccount.balance` is *available cash*; opening a position posts
  `notional / leverage` of it as the position's `margin`. At 1x leverage
  the margin is the whole notional, which is exactly this engine's original
  cash-only long accounting; every rule below reduces to it there.
- `average_entry_price` (on `PaperPosition`) is the VWAP of *fill* prices
  only (post-slippage, pre-fee) — fees are never blended into cost basis.
- **Opening/adding** posts margin and immediately realizes its own fee as a
  certain, already-paid cost: `realized_pnl -= fee_applied`. It does not
  otherwise realize any gain/loss.
- **Reducing/closing** realizes `(fill_price - average_entry_price) *
  quantity - fee_applied` for a long and `(average_entry_price - fill_price)
  * quantity - fee_applied` for a short, and returns the released share of
  the margin plus that PnL to cash. The return is floored at zero: isolated
  margin never loses more than was posted.
- **Funding** (`settle_funding`) is charged to available cash (or credited),
  and taken from the position's own margin only for the part cash cannot
  cover; it is part of `realized_pnl`.
- **Once every position an account has ever held is fully closed, `balance`
  exactly equals `starting_balance + realized_pnl`** — every dollar has
  either been posted-then-returned through a close (netting into a realized
  gain/loss) or never posted at all. While a position is still open, the
  two numbers don't (and shouldn't) reconcile: the difference is the
  margin still posted, which is neither a gain nor a loss yet.
- **Equity** = cash + every open position's margin + its unrealized PnL at
  the live price. It is what the limits below are measured against, never
  cash, which falls whenever margin is posted with no loss at all.

**Pre-trade risk limits, stated plainly:**

- **Halted check**: a halted account (drawdown limit breached) rejects any
  order that would *open or add to* a position until an explicit
  `resume_trading` call — see that method's own docstring for why it also
  resets `peak_balance` to the account's current equity. Orders that
  *reduce* a position, and triggered exits, are never blocked by the halt,
  and a liquidation cannot be blocked by anything.
- **Position sizing** (opening/adding orders): this order's *resulting*
  position **notional** at the *current* resolved quote (never the price a
  position was originally opened at) must not exceed `max_position_size_pct`
  of the account's *current equity*.
- **Exposure** (opening/adding orders): every other open position's
  *current* notional plus this order's own resulting notional must not
  exceed `max_exposure_pct` of the account's *current equity*. Leverage does
  not raise this ceiling: it only changes how much cash a position of a
  given notional ties up, and how close its liquidation price sits.
- **Leverage**: at most the account's `max_leverage`; leverage is fixed for a
  position's lifetime; a short or leveraged position above Delta's
  `max_leverage_notional` is rejected (margin scaling is not modelled).
- **Drawdown/halt**, evaluated *after* the trade completes, and again
  before any opening/adding order: `peak_balance` (the peak *equity*) only
  ever rises; if equity has fallen more than `max_drawdown_pct` below the
  (possibly just-raised) peak, `trading_halted` is set and an alert is
  raised. This can only ever flip `False -> True` here.

**Automated caller.** `user_id is None` is this method's own contract for
"the automated strategy" (a human caller always has one). An automated order
is refused anything but opening/adding to an unleveraged long or reducing a
long (`_enforce_automated_restrictions`), so the strategy — which this
module never lets know about shorts or leverage — cannot reach either, even
when it shares an account with a manually opened short.

**Concurrency**: the whole read-check-write sequence above is guarded by
`PaperAccountRepository.try_apply_trade_effects`, an atomic
`UPDATE ... WHERE balance = :expected AND trading_halted = :expected AND
state_version = :expected` (the version is what lets the guard see margin,
position and funding changes that leave cash untouched) —
the same core primitive `TrainingJobRepository.try_transition_to_running`
uses for its own check-then-act race, adapted into a bounded
retry-and-recompute loop because what this feature needs to guard
(current balance, current prices, every other open position) can't be
pinned to one fixed status value the way a training job's `'pending'`
can. See `place_order`'s own docstring for the full mechanics.

**Stop-loss / take-profit, stated plainly** (see
`app.paper_trading.monitor.StopLossTakeProfitMonitor` for the
event-driven side of this): a long's `stop_loss_price` must sit below the
current price and `take_profit_price` above it, and a short's the reverse
— either would trigger the instant it was set otherwise — and, whenever
both are present, the stop must sit on the far side of the take-profit
(`_validate_thresholds`), which keeps the two trigger conditions mutually
exclusive for every possible price, closing the "one tick crosses both"
question by construction rather than a runtime tie-break. A stop-loss must
also lie on the safe side of the position's **liquidation price**: one
placed beyond it could never fire, because the exchange liquidates first.
The monitor's own check order is liquidation, then stop-loss, then
take-profit — see `StopLossTakeProfitMonitor`'s docstring. A triggered
close (`trigger_close`) reuses the *same* `apply_fill_model` and the
*same* `try_apply_trade_effects` atomic guard `place_order` uses — so a
triggered auto-close racing a concurrent manual close of the same
position can never both succeed, exactly like the exposure-limit race
above, just applied to `PaperPosition.quantity` instead of
`PaperAccount.balance`/`trading_halted`. A liquidation is the same
mechanism with one difference in outcome: the whole remaining margin is
forfeited (cash returned: zero), and the loss is never charged beyond the
margin actually posted — if the mark price had already gapped past the
bankruptcy price, `gapped_through_bankruptcy` records it. The one deliberate difference:
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

import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.exc import IntegrityError

from app.models.paper_trading import PaperAccount, PaperFundingSettlement, PaperOrder, PaperPosition
from app.monitoring.error_tracking import capture_trading_halted
from app.paper_trading.base import FillQuote
from app.paper_trading.errors import (
    AccountUpdateConflictError,
    AutomatedOrderRestrictedError,
    InsufficientBalanceError,
    InvalidPaperOrderSortError,
    InvalidStopLossPriceError,
    InvalidTakeProfitPriceError,
    LeverageLimitExceededError,
    LeverageMismatchError,
    LeverageNotionalLimitError,
    MaxExposureExceededError,
    MaxPositionSizeExceededError,
    PaperAccountNotFoundError,
    PositionFlipError,
    PositionNotFoundError,
    ReduceOnlyViolationError,
    StopBeyondLiquidationError,
    StopLossNotBelowTakeProfitError,
    StrategyLeverageExceedsMaximumError,
    StrategyMissingTrainingJobError,
    StrategyStopBeyondLiquidationError,
    StrategyTrainingJobMissingSymbolError,
    ThresholdsOnReducingOrderError,
    TradingHaltedError,
)
from app.paper_trading.margin import (
    PositionSide,
    bankruptcy_price,
    effective_leverage,
    funding_payment,
    gapped_through_bankruptcy,
    initial_margin,
    is_liquidated,
    liquidation_distance_fraction,
    liquidation_price,
    unrealized_pnl,
)
from app.paper_trading.pricing import apply_fill_model, resolve_current_price
from app.repositories.audit_log import AuditLogRepository
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    ORDER_SORT_COLUMNS,
    LiquidationPriceFn,
    PaperAccountRepository,
    PaperFundingSettlementRepository,
    PaperOrderRepository,
    PaperPositionRepository,
    PaperStrategyDecisionRepository,
)
from app.repositories.training import TrainingJobRepository
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperAccountListResponse,
    PaperAccountResponse,
    PaperFundingSettlementListResponse,
    PaperFundingSettlementResponse,
    PaperOrderListResponse,
    PaperOrderRequest,
    PaperOrderResponse,
    PaperPositionDTO,
    PaperPositionListResponse,
    PaperStrategyConfigUpdateRequest,
    PaperStrategyDecisionListResponse,
    PaperStrategyDecisionResponse,
    PortfolioSummaryResponse,
    PositionThresholdsUpdateRequest,
    RiskSummaryResponse,
)
from app.services.market_query import MarketNotFoundError
from app.state.manager import MarketStateManager
from app.training.errors import TrainingJobNotFoundError

logger = logging.getLogger("app.services.paper_trading")

#: A nonzero exposure/position value against exactly-zero equity (a fully
#: wiped-out account, legitimately reachable without ever going negative)
#: has no finite "% of equity" — reported as this large, fixed sentinel
#: rather than raising `ZeroDivisionError`, since it's always unambiguously
#: over any limit that could ever be configured (<= 100%).
_ZERO_BALANCE_SENTINEL_PCT = Decimal("999999")

OrderKind = Literal["open", "increase", "reduce"]


@dataclass(frozen=True, slots=True)
class _Holdings:
    """What a set of open positions is worth to an account right now, at
    live prices: posted margin, unrealized PnL, and notional (absolute)."""

    margin: Decimal
    unrealized_pnl: Decimal
    notional: Decimal

    @property
    def equity_value(self) -> Decimal:
        return self.margin + self.unrealized_pnl


class PaperTradingService:
    """The one entry point routers use for every paper trading operation."""

    def __init__(
        self,
        account_repository: PaperAccountRepository,
        order_repository: PaperOrderRepository,
        position_repository: PaperPositionRepository,
        market_repository: MarketRepository,
        candle_repository: CandleRepository,
        training_job_repository: TrainingJobRepository,
        strategy_decision_repository: PaperStrategyDecisionRepository,
        audit_log_repository: AuditLogRepository,
        state_manager: MarketStateManager,
        slippage_bps: int,
        fee_bps: int,
        triggered_slippage_bps: int,
        staleness_threshold: timedelta,
        default_max_position_size_pct: Decimal,
        default_max_exposure_pct: Decimal,
        default_max_drawdown_pct: Decimal,
        max_order_attempts: int,
        default_strategy_confidence_threshold_pct: Decimal,
        default_strategy_default_stop_loss_pct: Decimal,
        default_max_leverage: Decimal = Decimal("5"),
        maintenance_margin_rate: Decimal = Decimal("0.0025"),
        max_leverage_notional: Decimal = Decimal("100000"),
        funding_settlement_repository: PaperFundingSettlementRepository | None = None,
        default_strategy_leverage: Decimal = Decimal("2"),
    ) -> None:
        self.account_repository = account_repository
        self.order_repository = order_repository
        self.position_repository = position_repository
        self.market_repository = market_repository
        self.candle_repository = candle_repository
        self.training_job_repository = training_job_repository
        self.strategy_decision_repository = strategy_decision_repository
        self.audit_log_repository = audit_log_repository
        self.state_manager = state_manager
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        self.triggered_slippage_bps = triggered_slippage_bps
        self.staleness_threshold = staleness_threshold
        self.default_max_position_size_pct = default_max_position_size_pct
        self.default_max_exposure_pct = default_max_exposure_pct
        self.default_max_drawdown_pct = default_max_drawdown_pct
        self.max_order_attempts = max_order_attempts
        self.default_strategy_confidence_threshold_pct = default_strategy_confidence_threshold_pct
        self.default_strategy_default_stop_loss_pct = default_strategy_default_stop_loss_pct
        # Margin/leverage configuration is optional on purpose: the automated
        # strategy builds its own service without ever naming any of it, and
        # must keep working unchanged (see `_enforce_automated_restrictions`
        # for why it can never reach leverage regardless of these values).
        # `maintenance_margin_rate` is a fraction (0.0025 = 0.25%), the form
        # `app.paper_trading.margin` takes.
        self.default_max_leverage = default_max_leverage
        self.maintenance_margin_rate = maintenance_margin_rate
        self.max_leverage_notional = max_leverage_notional
        self.funding_settlement_repository = funding_settlement_repository
        self.default_strategy_leverage = default_strategy_leverage

    async def create_account(
        self, request: PaperAccountCreateRequest, *, user_id: uuid.UUID
    ) -> PaperAccountResponse:
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
            max_leverage=(
                request.max_leverage
                if request.max_leverage is not None
                else self.default_max_leverage
            ),
            peak_balance=request.starting_balance,
            trading_halted=False,
            strategy_enabled=False,
            strategy_training_job_id=None,
            strategy_confidence_threshold_pct=self.default_strategy_confidence_threshold_pct,
            strategy_default_stop_loss_pct=self.default_strategy_default_stop_loss_pct,
            # Never above the account's own ceiling.
            strategy_leverage=min(
                self.default_strategy_leverage,
                request.max_leverage
                if request.max_leverage is not None
                else self.default_max_leverage,
            ),
        )
        created = await self.account_repository.create(account)
        logger.info(
            "Paper account created (account_id=%s name=%s starting_balance=%s "
            "max_position_size_pct=%s max_exposure_pct=%s max_drawdown_pct=%s "
            "max_leverage=%s strategy_leverage=%s strategy_enabled=%s)",
            created.id,
            created.name,
            created.starting_balance,
            created.max_position_size_pct,
            created.max_exposure_pct,
            created.max_drawdown_pct,
            created.max_leverage,
            created.strategy_leverage,
            created.strategy_enabled,
        )
        await self._record_audit(
            user_id=user_id,
            action="paper_account.create",
            resource_id=created.id,
            old_value=None,
            new_value={
                "name": created.name,
                "starting_balance": str(created.starting_balance),
                "max_position_size_pct": str(created.max_position_size_pct),
                "max_exposure_pct": str(created.max_exposure_pct),
                "max_drawdown_pct": str(created.max_drawdown_pct),
                "max_leverage": str(created.max_leverage),
            },
        )
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
        self,
        account_id: uuid.UUID,
        request: PaperOrderRequest,
        *,
        user_id: uuid.UUID | None = None,
        automated: bool = False,
    ) -> PaperOrderResponse:
        """Fill one market order immediately, completely, and realistically
        — guarded by pre-trade risk checks, with a drawdown/halt check
        applied after the fill.

        There is no pending/partial-fill state: every order either fills
        in full right now or is rejected outright (insufficient cash for the
        margin, an order that would reduce a position by more than it holds
        or flip it through zero, a breached risk limit — never partially
        executed). In one net position per market a buy opens/adds to a long
        or reduces a short, and a sell opens/adds to a short or reduces a
        long.

        **Concurrency.** Each attempt re-reads the account fresh, resolves
        a live price, re-evaluates every check, and finishes with a single
        atomic `UPDATE ... WHERE balance = :expected AND trading_halted =
        :expected AND state_version = :expected`
        (`PaperAccountRepository.try_apply_trade_effects`). That `UPDATE`
        only ever matches if nothing else has touched this account since
        this attempt's own read — exactly the guarantee
        `TrainingJobRepository.try_transition_to_running` gives its own
        duplicate-run race, just expressed as "the row is still what I
        last read" instead of "the row is still `'pending'`", because this
        feature's precondition depends on live prices and every other open
        position, not one fixed column. When it doesn't match (another
        order — a liquidation, a funding payment, or a resume — committed
        first), this attempt has *not* touched the position table yet, so
        nothing needs to be undone: it simply loops, re-reads the
        now-current account and positions, and recomputes every check from
        scratch — meaning two orders that would jointly breach a limit can
        never both succeed, because the second is re-evaluated against the
        first's already-committed effect, not the stale numbers it started
        with. Bounded at `max_order_attempts` (default 5) so a request is
        never left to loop forever; exhausting it raises
        `AccountUpdateConflictError`, practically unreachable by a real
        two-way race (one retry is always enough) but never assumed away.

        `user_id` names the authenticated caller for the audit trail
        (`app.services.audit`) — `None` for
        `PaperTradingStrategyScheduler`'s own automated orders, which have
        no human behind them to attribute and are already tracked in full
        via `PaperStrategyDecision` (`list_strategy_decisions`); no
        `audit_log` row is written for those.

        `automated=True` is the strategy's own explicit declaration (nothing
        is inferred from a missing `user_id`), and subjects the order to
        `_enforce_automated_restrictions`: an entry must use the account's
        fixed `strategy_leverage` and carry a stop-loss, and an automated
        order never adds to a position.

        **Exactly one of `user_id` and `automated=True` must be given.** An
        order that names neither would otherwise be treated as manual and
        escape every automated-order rule (the old inference gave it the
        strict rules by accident; an explicit flag must not turn a forgotten
        argument into the *lenient* path). Naming both is just as meaningless (a
        human and the strategy at once). Either raises before anything is read
        or written.
        """
        if (user_id is None) == (not automated):
            raise ValueError(
                "place_order needs exactly one of user_id (a manual, human-initiated order) "
                "or automated=True (the automated strategy); got "
                + ("both" if automated else "neither")
            )
        market = await self.market_repository.get_by_symbol(request.symbol)
        if market is None:
            raise MarketNotFoundError(request.symbol)

        for _attempt in range(self.max_order_attempts):
            account = await self._get_account_or_404(account_id)
            quote = await resolve_current_price(
                state_manager=self.state_manager,
                candle_repository=self.candle_repository,
                market_id=market.id,
                symbol=request.symbol,
                staleness_threshold=self.staleness_threshold,
            )

            position = await self.position_repository.get_by_account_and_symbol(
                account_id, request.symbol
            )
            held = Decimal(position.quantity) if position is not None else Decimal(0)
            held_side: PositionSide | None = (
                position.side if position is not None and held > 0 else None  # type: ignore[assignment]
            )
            kind, side = self._classify_order(request, held, held_side)
            increases = kind != "reduce"

            if request.reduce_only and increases:
                raise ReduceOnlyViolationError(request.symbol)
            if automated:
                self._enforce_automated_restrictions(
                    request=request,
                    kind=kind,
                    strategy_leverage=Decimal(account.strategy_leverage),
                )
            thresholds_named = (
                request.stop_loss_price is not None or request.take_profit_price is not None
            )
            if thresholds_named and not increases:
                raise ThresholdsOnReducingOrderError(request.symbol)

            balance = Decimal(account.balance)
            other_holdings = await self._holdings(account_id, exclude_symbol=request.symbol)
            own_holdings = self._own_holdings(position, held, quote.price)
            equity_before = balance + other_holdings.equity_value + own_holdings.equity_value

            if increases:
                if account.trading_halted:
                    raise TradingHaltedError(
                        equity_before, account.peak_balance, account.max_drawdown_pct
                    )
                peak_before, breached = self._apply_drawdown_tracking(account, equity_before)
                if breached:
                    # Unrealized losses count: an account already past its
                    # drawdown limit must not be allowed to take on more risk
                    # just because nothing has traded since it got there.
                    persisted = await self.account_repository.try_apply_trade_effects(
                        account_id,
                        expected_balance=account.balance,
                        expected_trading_halted=account.trading_halted,
                        expected_state_version=account.state_version,
                        new_balance=balance,
                        new_realized_pnl=Decimal(account.realized_pnl),
                        new_peak_balance=peak_before,
                        new_trading_halted=True,
                    )
                    if persisted is None:
                        continue  # lost a race — re-read and re-decide
                    self._alert_halted(
                        account_id, account.max_drawdown_pct, equity_before, peak_before
                    )
                    raise TradingHaltedError(equity_before, peak_before, account.max_drawdown_pct)

            leverage = self._resolve_leverage(
                kind=kind,
                request=request,
                position=position,
                account_max_leverage=Decimal(account.max_leverage),
            )
            fill = apply_fill_model(
                quote,
                side=request.side,
                quantity=request.quantity,
                slippage_bps=self.slippage_bps,
                fee_bps=self.fee_bps,
            )

            realized_pnl_this_order: Decimal | None = None
            effective_stop_loss_price: Decimal | None = None
            effective_take_profit_price: Decimal | None = None
            margin_after = Decimal(0)
            average_after = Decimal(0)
            margin_moved: Decimal
            if increases:
                margin_added = initial_margin(notional=fill.notional, leverage=leverage)
                total_cost = margin_added + fill.fee_applied
                if balance < total_cost:
                    raise InsufficientBalanceError(total_cost, balance)
                new_balance = balance - total_cost
                new_realized_pnl = Decimal(account.realized_pnl) - fill.fee_applied
                resulting_quantity = held + request.quantity
                previous_margin = Decimal(position.margin) if position is not None else Decimal(0)
                average_after = (
                    (
                        held * Decimal(position.average_entry_price)
                        + request.quantity * fill.fill_price
                    )
                    / resulting_quantity
                    if position is not None and held > 0
                    else fill.fill_price
                )
                margin_after = (previous_margin if held > 0 else Decimal(0)) + margin_added
                margin_moved = margin_added

                resulting_notional = resulting_quantity * quote.price
                if (leverage > 1 or side == "short") and resulting_notional > (
                    self.max_leverage_notional
                ):
                    raise LeverageNotionalLimitError(resulting_notional, self.max_leverage_notional)

                # --- Pre-trade risk checks: current price, current equity ---
                resulting_position_pct = self._percentage_of_equity(
                    resulting_notional, equity_before
                )
                max_position_pct = Decimal(account.max_position_size_pct)
                if resulting_position_pct > max_position_pct:
                    raise MaxPositionSizeExceededError(
                        request.symbol,
                        resulting_notional,
                        equity_before,
                        resulting_position_pct,
                        max_position_pct,
                    )
                resulting_exposure = other_holdings.notional + resulting_notional
                resulting_exposure_pct = self._percentage_of_equity(
                    resulting_exposure, equity_before
                )
                max_exposure_pct = Decimal(account.max_exposure_pct)
                if resulting_exposure_pct > max_exposure_pct:
                    raise MaxExposureExceededError(
                        resulting_exposure,
                        equity_before,
                        resulting_exposure_pct,
                        max_exposure_pct,
                    )

                resulting_liquidation = liquidation_price(
                    side=side,
                    entry_price=average_after,
                    quantity=resulting_quantity,
                    margin=margin_after,
                    maintenance_margin_rate=self.maintenance_margin_rate,
                )
                existing_stop_loss = (
                    Decimal(position.stop_loss_price)
                    if position is not None and held > 0 and position.stop_loss_price is not None
                    else None
                )
                existing_take_profit = (
                    Decimal(position.take_profit_price)
                    if position is not None and held > 0 and position.take_profit_price is not None
                    else None
                )
                # Merge: a value named in *this* request overrides; a field
                # this request doesn't mention keeps whatever the position
                # already had (never silently cleared by an order that never
                # mentioned it). The cross-check (stop vs take-profit) and
                # the stop-vs-liquidation check always run on the final,
                # merged pair — but the vs-current-price check only applies
                # to whichever field *this* request actually names, so an
                # untouched, already-valid threshold is never re-rejected
                # just because the price has since moved past it.
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
                    side=side,
                    current_price=quote.price,
                    stop_loss_price=effective_stop_loss_price,
                    take_profit_price=effective_take_profit_price,
                    liquidation=resulting_liquidation,
                    check_stop_loss_against_current_price=request.stop_loss_price is not None,
                    check_take_profit_against_current_price=request.take_profit_price is not None,
                )
            else:
                assert position is not None  # a reduce always has a position to reduce
                released = (
                    Decimal(position.margin)
                    if request.quantity == held
                    else Decimal(position.margin) * request.quantity / held
                )
                gross = unrealized_pnl(
                    side=side,
                    entry_price=Decimal(position.average_entry_price),
                    price=fill.fill_price,
                    quantity=request.quantity,
                )
                proceeds = max(Decimal(0), released + gross - fill.fee_applied)
                realized_pnl_this_order = proceeds - released
                new_balance = balance + proceeds
                new_realized_pnl = Decimal(account.realized_pnl) + realized_pnl_this_order
                resulting_quantity = held - request.quantity
                margin_after = Decimal(position.margin) - released
                average_after = Decimal(position.average_entry_price)
                margin_moved = released

            equity_after = (
                new_balance
                + other_holdings.equity_value
                + (
                    margin_after
                    + unrealized_pnl(
                        side=side,
                        entry_price=average_after,
                        price=quote.price,
                        quantity=resulting_quantity,
                    )
                    if resulting_quantity > 0
                    else Decimal(0)
                )
            )
            new_peak_balance, new_trading_halted = self._apply_drawdown_tracking(
                account, equity_after
            )
            # Read before the trade transaction commits: the alert below must
            # not depend on the ORM row still being loaded afterwards.
            newly_halted = new_trading_halted and not account.trading_halted
            max_drawdown_pct = account.max_drawdown_pct

            updated_account = await self.account_repository.try_apply_trade_effects(
                account_id,
                expected_balance=account.balance,
                expected_trading_halted=account.trading_halted,
                expected_state_version=account.state_version,
                new_balance=new_balance,
                new_realized_pnl=new_realized_pnl,
                new_peak_balance=new_peak_balance,
                new_trading_halted=new_trading_halted,
                commit=False,
            )
            if updated_account is None:
                continue  # lost the race — re-read and retry against fresh numbers

            # From here to `_commit_trade` is ONE transaction: the guarded
            # account update above holds the account row's lock until the
            # position and the order it gates have been written too.
            async with self._rollback_on_error():
                fill_time = datetime.now(UTC)
                if increases:
                    await self.position_repository.apply_open(
                        account_id,
                        request.symbol,
                        side=side,
                        quantity=request.quantity,
                        fill_price=fill.fill_price,
                        leverage=leverage,
                        margin_added=margin_moved,
                        liquidation_price_for=self._liquidation_price_fn(side),
                        opened_at=fill_time,
                        stop_loss_price=effective_stop_loss_price,
                        take_profit_price=effective_take_profit_price,
                        thresholds_provided=thresholds_named,
                        commit=False,
                    )
                else:
                    # A real invariant, not a defensive check: the reduce
                    # branch above already guarantees `position is not None`,
                    # restated because that narrowing doesn't survive the
                    # intervening code to this second, separate `if increases`.
                    assert position is not None
                    await self.position_repository.apply_reduce(
                        position, request.quantity, margin_released=margin_moved, commit=False
                    )

                order = PaperOrder(
                    account_id=account_id,
                    symbol=request.symbol,
                    side=request.side,
                    position_side=side,
                    leverage=leverage,
                    margin_applied=margin_moved,
                    reduce_only=request.reduce_only,
                    quantity=request.quantity,
                    raw_price=quote.price,
                    fill_price=fill.fill_price,
                    fill_time=fill_time,
                    price_source=quote.source,
                    price_observed_at=quote.observed_at,
                    is_stale_price=quote.is_stale,
                    slippage_applied=fill.slippage_applied,
                    fee_applied=fill.fee_applied,
                    notional=fill.notional,
                    realized_pnl=realized_pnl_this_order,
                )
                created = await self.order_repository.create(order, commit=False)
                await self._commit_trade(created)
            if newly_halted:
                self._alert_halted(account_id, max_drawdown_pct, equity_after, new_peak_balance)
            if user_id is not None:
                await self._record_audit(
                    user_id=user_id,
                    action="paper_account.place_order",
                    resource_id=account_id,
                    old_value=None,
                    new_value={
                        "order_id": str(created.id),
                        "symbol": created.symbol,
                        "side": created.side,
                        "position_side": created.position_side,
                        "leverage": str(created.leverage),
                        "margin_applied": str(created.margin_applied),
                        "reduce_only": created.reduce_only,
                        "quantity": str(created.quantity),
                        "fill_price": str(created.fill_price),
                        "notional": str(created.notional),
                        "fee_applied": str(created.fee_applied),
                    },
                )
            return PaperOrderResponse.from_model(created)

        raise AccountUpdateConflictError(self.max_order_attempts)

    async def trigger_close(
        self,
        account_id: uuid.UUID,
        symbol: str,
        *,
        reason: str,
        quote: FillQuote,
        price_basis: str | None = None,
    ) -> PaperOrderResponse | None:
        """Close `symbol` entirely for this account, market-triggered by a
        crossed stop-loss/take-profit threshold or by liquidation — called
        only by `app.paper_trading.monitor.StopLossTakeProfitMonitor`, never
        a router (there is no HTTP caller to report a rejection to, so this
        never raises; it returns `None` when there is nothing to do).

        Reuses `apply_fill_model` and `PaperAccountRepository
        .try_apply_trade_effects` — the exact same fill model and atomic
        concurrency guard `place_order` uses — but is otherwise its own,
        smaller loop rather than a shared code path with `place_order`,
        for one deliberate reason: this always closes *whatever is
        currently held*, re-read fresh on every retry attempt, not a
        fixed quantity decided once. That matters for the concurrency
        guarantee this method exists to provide — if a concurrent manual
        order partially (not fully) closes the position before this
        attempt's retry, the trigger adapts and closes the real
        remainder rather than failing on a now-stale, too-large number.
        `place_order`'s fixed, user-specified quantity is the right
        contract for a manual order; it would be the wrong one here.

        The closing order is a sell for a long and a buy for a short.
        `reason='liquidation'` differs in outcome, not in mechanism: the
        position's whole remaining margin is forfeited (D6: never generous),
        cash gets nothing back, and the loss is never charged beyond the
        margin actually posted. `quote` is the *mark* price for a
        liquidation; `price_basis` records whether it really was.

        Position-sizing/exposure are not checked: a full close only ever
        *reduces* both. **A halted account still accepts a triggered exit,
        and nothing can block a liquidation:** halting stops new risk from
        being taken, and refusing to close a position would leave an account
        that has just breached its drawdown limit fully exposed.
        """
        market = await self.market_repository.get_by_symbol(symbol)
        if market is None:
            return None

        for _attempt in range(self.max_order_attempts):
            account = await self._get_account_or_404(account_id)

            position = await self.position_repository.get_by_account_and_symbol(account_id, symbol)
            held = Decimal(position.quantity) if position is not None else Decimal(0)
            if held <= 0 or position is None:
                return None  # already closed — e.g. a concurrent manual close won

            side: PositionSide = position.side  # type: ignore[assignment]
            entry_price = Decimal(position.average_entry_price)
            margin = Decimal(position.margin)
            is_liquidation = reason == "liquidation"
            liquidation = (
                Decimal(position.liquidation_price)
                if position.liquidation_price is not None
                else None
            )
            if is_liquidation and not is_liquidated(
                side=side, mark_price=quote.price, liquidation=liquidation
            ):
                # The position changed since the monitor looked (a partial
                # close, or margin moved the liquidation price): re-judge it
                # against its *current* liquidation price, never a stale one.
                return None

            balance = Decimal(account.balance)
            fill = apply_fill_model(
                quote,
                side="sell" if side == "long" else "buy",
                quantity=held,
                slippage_bps=self.triggered_slippage_bps,
                fee_bps=self.fee_bps,
            )
            gapped = False
            if is_liquidation:
                gapped = gapped_through_bankruptcy(
                    side=side,
                    mark_price=quote.price,
                    bankruptcy=bankruptcy_price(
                        side=side, entry_price=entry_price, quantity=held, margin=margin
                    ),
                )
                proceeds = Decimal(0)
            else:
                gross = unrealized_pnl(
                    side=side, entry_price=entry_price, price=fill.fill_price, quantity=held
                )
                proceeds = max(Decimal(0), margin + gross - fill.fee_applied)
            realized_pnl_this_order = proceeds - margin
            new_balance = balance + proceeds
            new_realized_pnl = Decimal(account.realized_pnl) + realized_pnl_this_order

            other_holdings = await self._holdings(account_id, exclude_symbol=symbol)
            equity_after = new_balance + other_holdings.equity_value
            new_peak_balance, new_trading_halted = self._apply_drawdown_tracking(
                account, equity_after
            )
            # Read before the trade transaction commits: the alert below must
            # not depend on the ORM row still being loaded afterwards.
            newly_halted = new_trading_halted and not account.trading_halted
            max_drawdown_pct = account.max_drawdown_pct

            updated_account = await self.account_repository.try_apply_trade_effects(
                account_id,
                expected_balance=account.balance,
                expected_trading_halted=account.trading_halted,
                expected_state_version=account.state_version,
                new_balance=new_balance,
                new_realized_pnl=new_realized_pnl,
                new_peak_balance=new_peak_balance,
                new_trading_halted=new_trading_halted,
                commit=False,
            )
            if updated_account is None:
                continue  # lost the race — re-read the (possibly now-smaller) position and retry

            async with self._rollback_on_error():
                await self.position_repository.apply_reduce(
                    position, held, margin_released=margin, commit=False
                )

                order = PaperOrder(
                    account_id=account_id,
                    symbol=symbol,
                    side="sell" if side == "long" else "buy",
                    position_side=side,
                    leverage=Decimal(position.leverage),
                    margin_applied=margin,
                    reduce_only=True,
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
                    gapped_through_bankruptcy=gapped,
                    trigger_price_basis=price_basis if is_liquidation else None,
                )
                created = await self.order_repository.create(order, commit=False)
                await self._commit_trade(created)
            if is_liquidation:
                logger.warning(
                    "Paper position LIQUIDATED (account_id=%s symbol=%s side=%s quantity=%s "
                    "mark=%s liquidation_price=%s margin_forfeited=%s gapped_through_bankruptcy=%s "
                    "price_basis=%s)",
                    account_id,
                    symbol,
                    side,
                    held,
                    quote.price,
                    liquidation,
                    margin,
                    gapped,
                    price_basis,
                )
            if newly_halted:
                self._alert_halted(account_id, max_drawdown_pct, equity_after, new_peak_balance)
            return PaperOrderResponse.from_model(created)

        return None  # retries exhausted — the next price tick gives this another chance

    async def settle_funding(
        self,
        account_id: uuid.UUID,
        symbol: str,
        *,
        funding_time: datetime,
        funding_rate: Decimal,
        index_price: Decimal,
    ) -> PaperFundingSettlementResponse | None:
        """Charge (or credit) one open position its funding for one real
        funding time, exactly once. Returns `None` when there is nothing to
        do: no open position, a position opened after `funding_time` (it
        owed nothing then), or this `(account, symbol, funding_time)` already
        settled — which is what makes a repeated or catch-up run safe.

        `funding_rate` is a **fraction** (see `app.services.funding_rates`).
        The payment is charged to available cash first; only the part cash
        cannot cover is taken from the position's own margin, which moves
        its liquidation price (the position is then closer to liquidation, as
        it would be on the exchange). It is part of `realized_pnl`.

        **Idempotency.** The guarded account update, the settlement row
        (unique on `(account, symbol, funding_time)`) and any margin change are
        one transaction. Two concurrent runs for the same key can never both
        charge: the loser's guarded update waits for the winner's account row
        lock, then fails on the bumped version, re-reads, finds the key
        settled and returns; the unique key is a backstop that would undo the
        loser's update too. Nothing is ever half-applied.
        """
        if self.funding_settlement_repository is None:
            raise RuntimeError("settle_funding needs a funding_settlement_repository")
        repository = self.funding_settlement_repository

        for _attempt in range(self.max_order_attempts):
            account = await self._get_account_or_404(account_id)
            position = await self.position_repository.get_by_account_and_symbol(account_id, symbol)
            if position is None or Decimal(position.quantity) <= 0:
                return None
            opened_at = position.opened_at
            if opened_at is not None:
                opened = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=UTC)
                if opened >= funding_time:
                    return None  # opened after this funding time: owed nothing for it
            if await repository.exists(account_id, symbol, funding_time):
                return None

            side: PositionSide = position.side  # type: ignore[assignment]
            quantity = Decimal(position.quantity)
            payment = funding_payment(
                side=side, quantity=quantity, index_price=index_price, funding_rate=funding_rate
            )
            balance = Decimal(account.balance)
            from_cash = min(payment, balance) if payment > 0 else payment
            shortfall = payment - from_cash if payment > 0 else Decimal(0)
            new_balance = balance - from_cash
            new_margin = max(Decimal(0), Decimal(position.margin) - shortfall)

            other_holdings = await self._holdings(account_id, exclude_symbol=symbol)
            new_liquidation = liquidation_price(
                side=side,
                entry_price=Decimal(position.average_entry_price),
                quantity=quantity,
                margin=new_margin,
                maintenance_margin_rate=self.maintenance_margin_rate,
            )
            quote = await self._current_price_for_symbol(symbol)
            own_value = (
                new_margin
                + unrealized_pnl(
                    side=side,
                    entry_price=Decimal(position.average_entry_price),
                    price=quote.price,
                    quantity=quantity,
                )
                if quote is not None
                else new_margin
            )
            equity_after = new_balance + other_holdings.equity_value + own_value
            new_peak_balance, new_trading_halted = self._apply_drawdown_tracking(
                account, equity_after
            )
            # Read before the trade transaction commits: the alert below must
            # not depend on the ORM row still being loaded afterwards.
            newly_halted = new_trading_halted and not account.trading_halted
            max_drawdown_pct = account.max_drawdown_pct

            settlement = PaperFundingSettlement(
                account_id=account_id,
                symbol=symbol,
                funding_time=funding_time,
                position_side=side,
                quantity=quantity,
                index_price=index_price,
                funding_rate=funding_rate,
                payment=payment,
                charged_to_margin=shortfall,
            )
            # One transaction, guard first: the guarded account update (which
            # takes the account row's lock), then the unique settlement row,
            # then any margin change, committed together or not at all.
            updated_account = await self.account_repository.try_apply_trade_effects(
                account_id,
                expected_balance=account.balance,
                expected_trading_halted=account.trading_halted,
                expected_state_version=account.state_version,
                new_balance=new_balance,
                new_realized_pnl=Decimal(account.realized_pnl) - payment,
                new_peak_balance=new_peak_balance,
                new_trading_halted=new_trading_halted,
                commit=False,
            )
            if updated_account is None:
                continue  # lost the race: re-read (a settled key now returns None) and retry

            async with self._rollback_on_error():
                try:
                    created = await repository.create(settlement, commit=False)
                except IntegrityError:
                    # Backstop for the unique key: undo the guarded update too.
                    await repository.session.rollback()
                    return None  # another run settled this key first

                if shortfall > 0:
                    await self.position_repository.apply_margin_change(
                        position, margin=new_margin, liquidation_price=new_liquidation, commit=False
                    )
                await self._commit_trade(created)
            if newly_halted:
                self._alert_halted(account_id, max_drawdown_pct, equity_after, new_peak_balance)
            logger.info(
                "Funding settled (account_id=%s symbol=%s funding_time=%s side=%s payment=%s "
                "from_margin=%s)",
                account_id,
                symbol,
                funding_time.isoformat(),
                side,
                payment,
                shortfall,
            )
            return PaperFundingSettlementResponse.from_model(created)

        raise AccountUpdateConflictError(self.max_order_attempts)

    async def update_position_thresholds(
        self,
        account_id: uuid.UUID,
        symbol: str,
        request: PositionThresholdsUpdateRequest,
        *,
        user_id: uuid.UUID,
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
            side=position.side,  # type: ignore[arg-type]
            current_price=quote.price,
            stop_loss_price=new_stop_loss_price,
            take_profit_price=new_take_profit_price,
            liquidation=(
                Decimal(position.liquidation_price)
                if position.liquidation_price is not None
                else None
            ),
            check_stop_loss_against_current_price="stop_loss_price" in fields,
            check_take_profit_against_current_price="take_profit_price" in fields,
        )

        old_stop_loss_price = position.stop_loss_price
        old_take_profit_price = position.take_profit_price
        updated = await self.position_repository.update(
            position,
            {"stop_loss_price": new_stop_loss_price, "take_profit_price": new_take_profit_price},
        )
        logger.info(
            "Position thresholds updated (account_id=%s symbol=%s "
            "stop_loss_price=%s->%s take_profit_price=%s->%s)",
            account_id,
            symbol,
            old_stop_loss_price,
            new_stop_loss_price,
            old_take_profit_price,
            new_take_profit_price,
        )
        await self._record_audit(
            user_id=user_id,
            action="paper_account.update_position_thresholds",
            resource_id=account_id,
            old_value={
                "symbol": symbol,
                "stop_loss_price": str(old_stop_loss_price) if old_stop_loss_price else None,
                "take_profit_price": (
                    str(old_take_profit_price) if old_take_profit_price else None
                ),
            },
            new_value={
                "symbol": symbol,
                "stop_loss_price": str(new_stop_loss_price) if new_stop_loss_price else None,
                "take_profit_price": (
                    str(new_take_profit_price) if new_take_profit_price else None
                ),
            },
        )
        return PaperPositionDTO.from_model(
            updated, current_price=quote.price, price_source=quote.source
        )

    async def update_strategy_config(
        self,
        account_id: uuid.UUID,
        request: PaperStrategyConfigUpdateRequest,
        *,
        user_id: uuid.UUID,
    ) -> PaperAccountResponse:
        """Enable/disable the automated strategy and tune its threshold/stop-loss.

        Only fields the request actually names (`model_fields_set`) are
        changed — the same partial-update idiom
        `update_position_thresholds` already uses — but validation always
        runs against the *final*, merged state: `strategy_enabled=True`
        with no `strategy_training_job_id` at all (neither already set
        nor named in this request) is rejected outright
        (`StrategyMissingTrainingJobError`), as is naming a job that
        doesn't exist (`TrainingJobNotFoundError`, reused from
        `app.training.errors` rather than duplicated) or one with no
        recorded `symbol` — a job never trained on real market data has
        no market for the strategy to predict for
        (`StrategyTrainingJobMissingSymbolError`). Disabling never
        requires any of this: an account can always be turned off,
        regardless of what its training job looks like.
        """
        account = await self._get_account_or_404(account_id)
        fields = request.model_dump(exclude_unset=True)

        new_enabled = fields.get("enabled", account.strategy_enabled)
        new_training_job_id = fields.get("training_job_id", account.strategy_training_job_id)
        new_confidence_threshold_pct = Decimal(
            fields.get("confidence_threshold_pct", account.strategy_confidence_threshold_pct)
        )
        new_default_stop_loss_pct = Decimal(
            fields.get("default_stop_loss_pct", account.strategy_default_stop_loss_pct)
        )
        new_leverage = Decimal(fields.get("leverage", account.strategy_leverage))

        # The strategy's leverage is one fixed number, and its mandatory
        # stop-loss must be able to fire before the exchange would liquidate
        # the position it protects — checked on the final, merged values so a
        # leverage change can't quietly invalidate an existing stop-loss.
        if new_leverage > Decimal(account.max_leverage):
            raise StrategyLeverageExceedsMaximumError(new_leverage, account.max_leverage)
        for side in ("long", "short"):
            distance = liquidation_distance_fraction(
                side=side,
                leverage=new_leverage,
                maintenance_margin_rate=self.maintenance_margin_rate,
            )
            if distance is not None and new_default_stop_loss_pct >= distance * Decimal(100):
                raise StrategyStopBeyondLiquidationError(
                    new_default_stop_loss_pct, new_leverage, distance * Decimal(100)
                )

        if new_enabled:
            if new_training_job_id is None:
                raise StrategyMissingTrainingJobError()
            job = await self.training_job_repository.get_by_id(new_training_job_id)
            if job is None:
                raise TrainingJobNotFoundError(new_training_job_id)
            if not job.symbol:
                raise StrategyTrainingJobMissingSymbolError(new_training_job_id)

        old_enabled = account.strategy_enabled
        old_training_job_id = account.strategy_training_job_id
        old_confidence_threshold_pct = account.strategy_confidence_threshold_pct
        old_default_stop_loss_pct = account.strategy_default_stop_loss_pct
        old_leverage = account.strategy_leverage

        updated = await self.account_repository.update(
            account,
            {
                "strategy_enabled": new_enabled,
                "strategy_training_job_id": new_training_job_id,
                "strategy_confidence_threshold_pct": new_confidence_threshold_pct,
                "strategy_default_stop_loss_pct": new_default_stop_loss_pct,
                "strategy_leverage": new_leverage,
            },
        )
        # `strategy_enabled` gets its own line, not just a field in the
        # generic summary below — this is the exact field a live account
        # can start (or stop) placing real automated orders from, and a
        # bare "enabled: false -> true" with no further context is what
        # left an earlier incident untraceable (no way to tell "enabled,
        # pointed at training job X" from a content-free toggle after the
        # fact). Always names the training job it's pointed at, not just
        # whether the flag flipped.
        if new_enabled != old_enabled:
            logger.info(
                "Paper trading strategy %s (account_id=%s training_job_id=%s "
                "confidence_threshold_pct=%s default_stop_loss_pct=%s leverage=%sx "
                "directions=long+short)",
                "ENABLED" if new_enabled else "DISABLED",
                account_id,
                new_training_job_id,
                new_confidence_threshold_pct,
                new_default_stop_loss_pct,
                new_leverage,
            )
            # Its own dedicated audit action too, mirroring the log line
            # above — the exact fact ("who enabled/disabled it, pointed at
            # which job") the motivating incident had no way to attribute
            # at all.
            await self._record_audit(
                user_id=user_id,
                action="paper_account.strategy_enabled",
                resource_id=account_id,
                old_value={
                    "enabled": old_enabled,
                    "training_job_id": str(old_training_job_id) if old_training_job_id else None,
                },
                new_value={
                    "enabled": new_enabled,
                    "training_job_id": str(new_training_job_id) if new_training_job_id else None,
                },
            )
        logger.info(
            "Paper trading strategy config updated (account_id=%s "
            "enabled=%s->%s training_job_id=%s->%s "
            "confidence_threshold_pct=%s->%s default_stop_loss_pct=%s->%s leverage=%s->%s)",
            account_id,
            old_enabled,
            new_enabled,
            old_training_job_id,
            new_training_job_id,
            old_confidence_threshold_pct,
            new_confidence_threshold_pct,
            old_default_stop_loss_pct,
            new_default_stop_loss_pct,
            old_leverage,
            new_leverage,
        )
        await self._record_audit(
            user_id=user_id,
            action="paper_account.update_strategy_config",
            resource_id=account_id,
            old_value={
                "enabled": old_enabled,
                "training_job_id": str(old_training_job_id) if old_training_job_id else None,
                "confidence_threshold_pct": str(old_confidence_threshold_pct),
                "default_stop_loss_pct": str(old_default_stop_loss_pct),
                "leverage": str(old_leverage),
            },
            new_value={
                "enabled": new_enabled,
                "training_job_id": str(new_training_job_id) if new_training_job_id else None,
                "confidence_threshold_pct": str(new_confidence_threshold_pct),
                "default_stop_loss_pct": str(new_default_stop_loss_pct),
                "leverage": str(new_leverage),
            },
        )
        return PaperAccountResponse.from_model(updated)

    async def list_strategy_decisions(
        self, account_id: uuid.UUID, *, limit: int, offset: int
    ) -> PaperStrategyDecisionListResponse:
        """One page of an account's own automated-strategy decision log,
        most recent first — the Strategy panel's decision log data
        source, populated by `app.services.paper_trading_strategy
        .PaperTradingStrategyScheduler`, never by this method itself."""
        await self._get_account_or_404(account_id)
        decisions, total = await self.strategy_decision_repository.list_for_account(
            account_id, limit=limit, offset=offset
        )
        return PaperStrategyDecisionListResponse(
            decisions=[PaperStrategyDecisionResponse.from_model(d) for d in decisions],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def resume_trading(
        self, account_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> PaperAccountResponse:
        """Explicitly clear a drawdown halt — the *only* way it ever
        clears (this feature's own spec: no self-healing on balance
        recovery — nothing about *this* trade or any later one ever
        clears `trading_halted` on its own; only this explicit call does).

        `peak_balance` (the peak *equity*) is reset to the account's current
        equity as part of the same action. Without that, an account resumed
        while still deep in drawdown against its old, untouched peak would
        measure straight back below the same threshold and re-halt after its
        very next order — regardless of that order's own direction or
        size — making "resume" nearly indistinguishable from "allow
        exactly one more order." Resetting the high-water mark to *now*
        is what a manual risk override conventionally means: the account
        starts being measured fresh from the point someone explicitly
        vouched for it, not from a peak that trade already lost.
        """
        account = await self._get_account_or_404(account_id)
        old_trading_halted = account.trading_halted
        old_peak_balance = account.peak_balance
        equity = await self._account_equity(account)
        updated = await self.account_repository.update(
            account, {"trading_halted": False, "peak_balance": equity}
        )
        logger.info(
            "Paper trading resumed (account_id=%s trading_halted=%s->False peak_balance=%s->%s)",
            account_id,
            old_trading_halted,
            old_peak_balance,
            equity,
        )
        await self._record_audit(
            user_id=user_id,
            action="paper_account.resume_trading",
            resource_id=account_id,
            old_value={"trading_halted": old_trading_halted, "peak_balance": str(old_peak_balance)},
            new_value={"trading_halted": False, "peak_balance": str(equity)},
        )
        return PaperAccountResponse.from_model(updated)

    async def risk_summary(self, account_id: uuid.UUID) -> RiskSummaryResponse:
        """This account's own current exposure and drawdown against its
        configured limits, and whether trading is halted — computed fresh
        against live prices on every read, exactly like `summary`'s own
        `unrealized_pnl`, never stored. Exposure is open **notional** as a
        % of **equity**, and drawdown is **equity** against its peak (never
        cash, which falls whenever margin is posted)."""
        account = await self._get_account_or_404(account_id)
        balance = Decimal(account.balance)
        peak_balance = Decimal(account.peak_balance)

        holdings = await self._holdings(account_id)
        equity = balance + holdings.equity_value
        current_exposure_pct = self._percentage_of_equity(holdings.notional, equity)
        # Equity can sit above the stored peak between events (the peak only
        # moves when something trades), which is not a negative drawdown.
        current_drawdown_pct = (
            Decimal(0)
            if peak_balance == 0
            else max(Decimal(0), ((peak_balance - equity) / peak_balance) * Decimal(100))
        )
        max_exposure_pct = Decimal(account.max_exposure_pct)
        max_drawdown_pct = Decimal(account.max_drawdown_pct)

        return RiskSummaryResponse(
            account_id=str(account.id),
            balance=balance,
            equity=equity,
            margin_in_use=holdings.margin,
            peak_balance=peak_balance,
            total_notional=holdings.notional,
            effective_leverage=effective_leverage(notional=holdings.notional, equity=equity),
            current_exposure_pct=current_exposure_pct,
            max_exposure_pct=max_exposure_pct,
            exposure_headroom_pct=max_exposure_pct - current_exposure_pct,
            current_drawdown_pct=current_drawdown_pct,
            max_drawdown_pct=max_drawdown_pct,
            drawdown_headroom_pct=max_drawdown_pct - current_drawdown_pct,
            max_position_size_pct=Decimal(account.max_position_size_pct),
            max_leverage=Decimal(account.max_leverage),
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
        unrealized = sum((p.unrealized_pnl for p in positions), Decimal(0))
        margin_in_use = sum((p.margin for p in positions), Decimal(0))
        notional = sum((p.current_price * p.quantity for p in positions), Decimal(0))
        equity = Decimal(account.balance) + margin_in_use + unrealized
        return PortfolioSummaryResponse(
            account_id=str(account.id),
            balance=account.balance,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=unrealized,
            margin_in_use=margin_in_use,
            total_equity=equity,
            total_notional=notional,
            effective_leverage=effective_leverage(notional=notional, equity=equity),
            open_position_count=len(positions),
        )

    async def list_funding_settlements(
        self, account_id: uuid.UUID, *, limit: int, offset: int
    ) -> PaperFundingSettlementListResponse:
        """One page of an account's funding payments, most recent first."""
        if self.funding_settlement_repository is None:
            raise RuntimeError("list_funding_settlements needs a funding_settlement_repository")
        await self._get_account_or_404(account_id)
        rows, total = await self.funding_settlement_repository.list_for_account(
            account_id, limit=limit, offset=offset
        )
        return PaperFundingSettlementListResponse(
            settlements=[PaperFundingSettlementResponse.from_model(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def _get_account_or_404(self, account_id: uuid.UUID) -> PaperAccount:
        account = await self.account_repository.get_by_id(account_id)
        if account is None:
            raise PaperAccountNotFoundError(account_id)
        return account

    async def _record_audit(
        self,
        *,
        user_id: uuid.UUID,
        action: str,
        resource_id: uuid.UUID,
        old_value: dict[str, object] | None,
        new_value: dict[str, object] | None,
    ) -> None:
        """The one place this service writes an `audit_log` row — every
        value passed in is already a plain, JSON-serializable dict (the
        caller stringifies any `Decimal` first, matching this platform's
        own `order_flow.py` convention for the same JSON-column
        constraint)."""
        await self.audit_log_repository.create(
            user_id=user_id,
            action=action,
            resource_type="paper_account",
            resource_id=str(resource_id),
            old_value=old_value,
            new_value=new_value,
        )

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

    @contextlib.asynccontextmanager
    async def _rollback_on_error(self) -> AsyncIterator[None]:
        """Roll the open trade transaction back if anything in it raises, so a
        failed flush never leaves a long-lived session stuck mid-transaction
        (the automated strategy shares one session across a whole tick)."""
        try:
            yield
        except BaseException:
            await self.account_repository.session.rollback()
            raise

    async def _commit_trade(self, *created: object) -> None:
        """Commit the transaction a guarded trade effect opened (the account
        update, the position write and the order/settlement row together),
        and reload what was created for its server-side defaults. Rolls the
        whole thing back if any of it fails."""
        session = self.account_repository.session
        try:
            await session.commit()
            for instance in created:
                await session.refresh(instance)
        except BaseException:
            await session.rollback()
            raise

    async def _holdings(
        self, account_id: uuid.UUID, *, exclude_symbol: str | None = None
    ) -> _Holdings:
        """Every open position's margin, unrealized PnL and notional at the
        *live* price (the same live-price-with-fallback quote a fill would
        use), summed. `exclude_symbol` lets `place_order` value the symbol
        it's about to trade separately, from its own already-resolved quote
        and *resulting* quantity, instead of the stored pre-trade one."""
        positions = await self.position_repository.list_open(account_id)
        margin = Decimal(0)
        pnl = Decimal(0)
        notional = Decimal(0)
        for position in positions:
            if position.symbol == exclude_symbol:
                continue
            quote = await self._current_price_for_symbol(position.symbol)
            if quote is None:
                continue
            quantity = Decimal(position.quantity)
            margin += Decimal(position.margin)
            pnl += unrealized_pnl(
                side=position.side,  # type: ignore[arg-type]
                entry_price=Decimal(position.average_entry_price),
                price=quote.price,
                quantity=quantity,
            )
            notional += quantity * quote.price
        return _Holdings(margin=margin, unrealized_pnl=pnl, notional=notional)

    @staticmethod
    def _own_holdings(position: PaperPosition | None, held: Decimal, price: Decimal) -> _Holdings:
        """The one position `place_order` is trading, valued at `price`."""
        if position is None or held <= 0:
            return _Holdings(Decimal(0), Decimal(0), Decimal(0))
        return _Holdings(
            margin=Decimal(position.margin),
            unrealized_pnl=unrealized_pnl(
                side=position.side,  # type: ignore[arg-type]
                entry_price=Decimal(position.average_entry_price),
                price=price,
                quantity=held,
            ),
            notional=held * price,
        )

    async def _account_equity(self, account: PaperAccount) -> Decimal:
        """Cash + every open position's margin + unrealized PnL, live."""
        holdings = await self._holdings(account.id)
        return Decimal(account.balance) + holdings.equity_value

    @staticmethod
    def _percentage_of_equity(value: Decimal, equity: Decimal) -> Decimal:
        """`value` as a percentage of `equity` — `_ZERO_BALANCE_SENTINEL_PCT`
        (never a `ZeroDivisionError`) for the rare zero-or-negative-equity case."""
        if equity <= 0:
            return Decimal(0) if value == 0 else _ZERO_BALANCE_SENTINEL_PCT
        return (value / equity) * Decimal(100)

    @staticmethod
    def _apply_drawdown_tracking(account: PaperAccount, equity: Decimal) -> tuple[Decimal, bool]:
        """Peak-equity tracking and the drawdown halt, evaluated fresh
        after every event that changes equity (a fill, a triggered close, a
        liquidation, a funding payment) and before any order that would add
        risk. `peak_balance` (the peak *equity*) only ever rises;
        `trading_halted` can only flip `False -> True` here — an account
        already halted stays halted, and only `resume_trading` clears it."""
        new_peak = max(Decimal(account.peak_balance), equity)
        threshold = new_peak * (Decimal(1) - Decimal(account.max_drawdown_pct) / Decimal(100))
        breached = equity < threshold
        return new_peak, account.trading_halted or breached

    @staticmethod
    def _classify_order(
        request: PaperOrderRequest, held: Decimal, held_side: PositionSide | None
    ) -> tuple[OrderKind, PositionSide]:
        """What this order does to the position: `open` a new one, `increase`
        the existing one, or `reduce` it — and which side the position is.

        An order on the opposite side of an existing position reduces it,
        and one larger than the position would carry it through zero into the
        opposite side in a single step, which is rejected (`PositionFlipError`):
        Delta's behaviour there is undocumented, so the conservative,
        auditable choice is to make the caller close first and open the other
        side with a separate order.
        """
        order_side: PositionSide = "long" if request.side == "buy" else "short"
        if held_side is None:
            return "open", order_side
        if order_side == held_side:
            return "increase", held_side
        if request.quantity > held:
            raise PositionFlipError(request.symbol, request.quantity, held)
        return "reduce", held_side

    @staticmethod
    def _enforce_automated_restrictions(
        *, request: PaperOrderRequest, kind: OrderKind, strategy_leverage: Decimal
    ) -> None:
        """What the automated strategy may do on the one order path it shares
        with manual orders, whichever direction it trades.

        - It **opens** a position (long or short) or **closes** one. It never
          adds to one, which its own logic never does either.
        - An entry must use **exactly the account's `strategy_leverage`**: the
          single fixed number this feature allows, never anything else, and
          never something the caller worked out from a prediction. A request
          that names no leverage means 1x and is refused unless 1x is what is
          configured.
        - An entry must carry a **stop-loss**. The strategy always passes one;
          this makes it non-optional at the shared path too, so an automated
          position without a stop-loss cannot be created by any caller.
        - A close (a reduction) is always allowed: it only lowers risk. The
          strategy sends it `reduce_only`, so a close that loses a race to a
          stop-loss or liquidation fails instead of opening the opposite side.

        Everything else (the halt, position size, exposure, drawdown, the
        stop-loss's own validity against the price and the liquidation price)
        is applied to an automated order by the same code as a manual one. A
        refusal here is a logged `no_action` in the strategy's decision log.
        """
        if kind == "reduce":
            return
        if kind == "increase":
            raise AutomatedOrderRestrictedError(
                "it opens a position or closes one; it never adds to one"
            )
        requested = request.leverage if request.leverage is not None else Decimal(1)
        if requested != strategy_leverage:
            raise AutomatedOrderRestrictedError(
                f"entries use the account's fixed strategy_leverage ({strategy_leverage}x), "
                f"not {requested}x"
            )
        if request.stop_loss_price is None:
            raise AutomatedOrderRestrictedError("every automated entry must carry a stop-loss")

    def _resolve_leverage(
        self,
        *,
        kind: OrderKind,
        request: PaperOrderRequest,
        position: PaperPosition | None,
        account_max_leverage: Decimal,
    ) -> Decimal:
        """The leverage this order acts at: the request's (default 1x) for a
        new position, the position's own for an add (naming a different one
        is rejected: leverage is fixed while a position is open), and the
        position's own for a reduce (the request's is irrelevant)."""
        if kind == "open":
            leverage = request.leverage if request.leverage is not None else Decimal(1)
            if leverage > account_max_leverage:
                raise LeverageLimitExceededError(leverage, account_max_leverage)
            return leverage
        assert position is not None
        position_leverage = Decimal(position.leverage)
        if (
            kind == "increase"
            and request.leverage is not None
            and request.leverage != position_leverage
        ):
            raise LeverageMismatchError(request.symbol, request.leverage, position_leverage)
        return position_leverage

    def _liquidation_price_fn(self, side: PositionSide) -> LiquidationPriceFn:
        rate = self.maintenance_margin_rate

        def compute(entry_price: Decimal, quantity: Decimal, margin: Decimal) -> Decimal | None:
            return liquidation_price(
                side=side,
                entry_price=entry_price,
                quantity=quantity,
                margin=margin,
                maintenance_margin_rate=rate,
            )

        return compute

    @staticmethod
    def _alert_halted(
        account_id: uuid.UUID, max_drawdown_pct: object, equity: Decimal, peak: Decimal
    ) -> None:
        """The kill switch's alert (D4): a halt blocks new risk, and this
        makes sure a person finds out it happened. Takes plain values, never
        an ORM row, so it is safe to call after the transaction that made it
        has committed."""
        capture_trading_halted(
            str(account_id),
            equity=equity,
            peak_equity=peak,
            max_drawdown_pct=max_drawdown_pct,
        )

    @staticmethod
    def _validate_thresholds(
        *,
        side: PositionSide,
        current_price: Decimal,
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        liquidation: Decimal | None,
        check_stop_loss_against_current_price: bool,
        check_take_profit_against_current_price: bool,
    ) -> None:
        """A long's stop-loss must sit below `current_price` and its
        take-profit above it (a short's, the reverse) — either would
        trigger the instant it's set otherwise. That check only applies to
        whichever of the two *this* call is actually setting
        (`check_stop_loss_against_current_price`/
        `check_take_profit_against_current_price` — false for a field
        merely carried over, unmentioned, from the position's existing
        value): an untouched, already-valid threshold must never be
        re-rejected just because the price has since moved past it — that
        would make an unrelated order (or an update to the *other*
        threshold) fail for a reason it never asked about.

        The cross-check is different: whenever both are present in the
        *final*, merged pair — touched or not — the stop-loss must be on
        the far side of the take-profit (below it for a long, above it for
        a short). Each was independently valid against its own current
        price at whatever moment it was set, but that alone doesn't stop a
        high stop-loss and a low take-profit being set at two different
        times as the price moved between them — this is what actually
        closes that gap, keeping the two trigger conditions mutually
        exclusive for every possible price. See `app.paper_trading.monitor`'s
        own docstring for why that's this feature's actual answer to "what
        if one tick crosses both."

        Finally a stop-loss must lie on the safe side of the position's
        **liquidation price** (above it for a long, below it for a short): one
        beyond it could never fire, because the exchange liquidates the
        position first. Checked on the final stop whether or not this call
        touched it, since an add can move the liquidation price past a stop
        that was valid when it was set.
        """
        is_long = side == "long"
        if check_stop_loss_against_current_price and stop_loss_price is not None:
            wrong = (
                stop_loss_price >= current_price if is_long else stop_loss_price <= current_price
            )
            if wrong:
                raise InvalidStopLossPriceError(stop_loss_price, current_price, side)
        if check_take_profit_against_current_price and take_profit_price is not None:
            wrong = (
                take_profit_price <= current_price
                if is_long
                else take_profit_price >= current_price
            )
            if wrong:
                raise InvalidTakeProfitPriceError(take_profit_price, current_price, side)
        if stop_loss_price is not None and take_profit_price is not None:
            crossed = (
                stop_loss_price >= take_profit_price
                if is_long
                else stop_loss_price <= take_profit_price
            )
            if crossed:
                raise StopLossNotBelowTakeProfitError(stop_loss_price, take_profit_price, side)
        if stop_loss_price is not None and liquidation is not None:
            beyond = stop_loss_price <= liquidation if is_long else stop_loss_price >= liquidation
            if beyond:
                raise StopBeyondLiquidationError(stop_loss_price, liquidation, side)
