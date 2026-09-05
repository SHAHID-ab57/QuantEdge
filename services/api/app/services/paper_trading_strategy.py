"""Periodic execution of each account's own, optional automated strategy.

Mirrors `app.services.candle_sync.CandleSyncScheduler` /
`app.services.grading_scheduler.PredictionGradingScheduler` exactly: a
single `asyncio` loop task, its own database session per tick (never a
request-scoped one — there is no request here), an enable flag gating
whether the *loop* runs at all, isolated per-account failures, and
`run_strategy_once` — a synchronous one-off entry point for ops/manual
verification, the same role `run_sync_once`/`run_grading_once` play for
their own schedulers.

**Off by default, explicit per-account opt-in.** This module's own
`paper_trading_strategy_scheduler_enabled` setting only gates whether
the loop *itself* runs — the real opt-in is `PaperAccount
.strategy_enabled` (default `False`), read fresh from the database at
the top of every single tick (`PaperAccountRepository
.list_strategy_enabled`), never cached across ticks. A running loop
with every account disabled does nothing at all, tick after tick,
forever — and an account whose strategy is disabled mid-cycle is simply
absent from the *next* tick's query, which is exactly what "disabling
takes effect before the next cycle" means here.

**"Just another caller" of the existing order-placement path.** Every
order this scheduler ever places goes through the exact same
`PaperTradingService.place_order` a manual order from the API/UI uses —
the same halted check, the same position-sizing and exposure checks
against live prices, and the same atomic `try_apply_trade_effects`
concurrency guard. This module never mutates a balance or a position
directly, and never constructs a second, parallel fill path — see
`tests/paper_trading/test_strategy_scheduler.py::TestSharesExistingRiskLimits`
for the test proving a strategy order is rejected the identical way a
manual one would be when it would breach a configured risk limit.

**The decision, stated plainly.** Each tick, for every account with
`strategy_enabled=True`:

1. Resolve the account's own `strategy_training_job_id`. Missing,
   deleted, or trained without a recorded `symbol` (never trained on
   real market data) — logged `no_action`, nothing else attempted.
2. Request a fresh prediction (`PredictionService.run`, the exact same
   live-inference path `POST /predictions/run` uses) for that job's own
   recorded `symbol` — never a separately-configured one, so a strategy
   can never accidentally predict one market and trade another. Any
   failure (job not completed, no candle history, feature mismatch,
   ...) — logged `no_action` with the failure reason.
3. No `confidence` at all (an unsupported model kind) — logged
   `no_action`. Below `strategy_confidence_threshold_pct` — logged
   `no_action`.
4. Interpret `predicted_value`: `"up"` is bullish, `"down"` is bearish,
   anything else (`"flat"`, a regressor's own number, ...) is not a
   directional call — logged `no_action`. Flat + bullish opens a
   position (a buy, sized at half the account's own
   `max_position_size_pct` of current balance — deliberately
   conservative headroom for slippage/fee and any other open exposure,
   since there is no separate strategy-specific position-sizing config
   — with a stop-loss attached at `strategy_default_stop_loss_pct`
   below the resolved price: `place_order`'s own
   `InvalidStopLossPriceError` is the backstop if the price has moved
   by fill time, itself logged `no_action` rather than raised anywhere).
   Long + bearish closes it (a sell for the full held quantity). Long +
   bullish and flat + bearish are both "no consistent change" — logged
   `no_action`, never a short: this platform is long-only,
   unconditionally, for an automated order exactly as for a manual one.

Every one of these outcomes — including the ones that place no order —
is persisted as exactly one `PaperStrategyDecision` row per
strategy-enabled account per tick: the Strategy panel's own decision
log data source (`GET .../strategy/decisions`), and this module's actual
answer to "log every cycle, acted or not, and why."
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.engine import get_engine
from app.dependencies.prediction import get_prediction_service
from app.models.paper_trading import PaperAccount, PaperStrategyDecision
from app.paper_trading.errors import NoPriceAvailableError
from app.paper_trading.pricing import resolve_current_price
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
    PaperStrategyDecisionRepository,
)
from app.repositories.training import TrainingJobRepository
from app.schemas.paper_trading import PaperOrderRequest
from app.schemas.prediction import PredictionResponse, PredictionRunRequest
from app.services.paper_trading import PaperTradingService
from app.state.manager import MarketStateManager

logger = logging.getLogger("app.services.paper_trading_strategy")

#: The automated strategy has no separate position-sizing config of its
#: own (only a confidence threshold and a stop-loss %) — it targets this
#: fraction of the account's own `max_position_size_pct`, leaving
#: headroom for slippage/fee and any other open exposure while still
#: being fully subject to the same position-size/exposure checks a
#: manual order faces.
_TARGET_POSITION_SIZE_FRACTION = Decimal("0.5")


@dataclass(frozen=True)
class StrategyTickSummary:
    """Outcome of one strategy pass, plus how long it took."""

    attempted: int
    opened: int
    closed: int
    no_action: int
    duration_seconds: float


class PaperTradingStrategyScheduler:
    """Periodic execution of every strategy-enabled account's own
    automated strategy.

    Args:
        state_manager: the process-wide `MarketStateManager` — the same
            live price state `PaperTradingService.place_order` itself
            reads from, never a second market-data path.
        interval_seconds: delay between ticks.
    """

    def __init__(self, *, state_manager: MarketStateManager, interval_seconds: int = 300) -> None:
        self._state_manager = state_manager
        self._interval_seconds = max(interval_seconds, 1)
        self._stopped = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """True while the background loop task is alive."""
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Begin the periodic loop, running the first tick immediately."""
        if self.running:
            return
        if get_engine() is None:
            logger.warning("Paper trading strategy scheduler not started: database not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="paper-trading-strategy-loop")
        logger.info(
            "Paper trading strategy scheduler started (interval=%ss)", self._interval_seconds
        )

    async def stop(self) -> None:
        """Stop the loop, cancelling any in-flight tick."""
        task = self._task
        if task is None:
            return
        self._stopped.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        logger.info("Paper trading strategy scheduler stopped")

    async def _loop(self) -> None:
        """Run ticks back-to-back until stopped."""
        while not self._stopped.is_set():
            started = perf_counter()
            summary = await self.run_strategy_tick()
            if summary.attempted > 0:
                logger.info(
                    "Paper trading strategy tick: opened=%d closed=%d no_action=%d in %.2fs",
                    summary.opened,
                    summary.closed,
                    summary.no_action,
                    perf_counter() - started,
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)

    async def run_strategy_tick(self) -> StrategyTickSummary:
        """Run one tick: every strategy-enabled account, once, in isolation.

        Opens its own session bound to the process-wide engine — the
        same `get_engine()`-gated pattern every other scheduler on this
        platform already uses. `PaperAccountRepository
        .list_strategy_enabled` is read fresh here, at the top of the
        tick — never cached — so a disabled account is simply absent
        from this query on its very next tick.
        """
        started = perf_counter()
        engine = get_engine()
        if engine is None:
            logger.warning("Paper trading strategy skipped: database is not configured")
            return StrategyTickSummary(0, 0, 0, 0, 0.0)

        settings = get_settings()
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            accounts = await PaperAccountRepository(session).list_strategy_enabled()
            opened = closed = no_action = 0
            for account in accounts:
                outcome = await self._process_account(session, account, settings)
                if outcome == "opened":
                    opened += 1
                elif outcome == "closed":
                    closed += 1
                else:
                    no_action += 1

        return StrategyTickSummary(
            attempted=len(accounts),
            opened=opened,
            closed=closed,
            no_action=no_action,
            duration_seconds=perf_counter() - started,
        )

    async def _process_account(
        self, session: AsyncSession, account: PaperAccount, settings: Settings
    ) -> str:
        """Handle one account's own cycle, start to finish, in isolation —
        any failure here is caught and logged as a `no_action` decision
        rather than allowed to stop the rest of this tick's accounts, the
        same per-item isolation `CandleSyncScheduler`/
        `StopLossTakeProfitMonitor` already apply to their own loops."""
        decision_repository = PaperStrategyDecisionRepository(session)
        confidence_threshold_pct = Decimal(account.strategy_confidence_threshold_pct)
        job_id = account.strategy_training_job_id

        async def log_no_action(
            *,
            symbol: str | None = None,
            reason: str,
            predicted_value: object | None = None,
            confidence: float | None = None,
            prediction_id: uuid.UUID | None = None,
        ) -> str:
            await decision_repository.create(
                _build_decision(
                    account_id=account.id,
                    training_job_id=job_id,
                    symbol=symbol,
                    action="no_action",
                    reason=reason[:500],
                    predicted_value=predicted_value,
                    confidence=confidence,
                    confidence_threshold_pct=confidence_threshold_pct,
                    prediction_id=prediction_id,
                    order_id=None,
                )
            )
            return "no_action"

        try:
            if job_id is None:
                return await log_no_action(
                    reason="No training job configured for this account's strategy."
                )

            job = await TrainingJobRepository(session).get_by_id(job_id)
            if job is None:
                return await log_no_action(
                    reason=f"Configured training job {job_id} no longer exists."
                )
            if not job.symbol:
                return await log_no_action(
                    reason=f"Training job {job_id} has no recorded symbol — it was not trained "
                    "on real market data."
                )
            symbol = job.symbol

            prediction_service = get_prediction_service(session)
            try:
                prediction = await prediction_service.run(
                    PredictionRunRequest(training_job_id=job_id, symbol=symbol)
                )
            except Exception as exc:  # noqa: BLE001 - isolated per account, never fatal
                return await log_no_action(symbol=symbol, reason=f"Prediction unavailable: {exc}")

            prediction_id = uuid.UUID(prediction.id)
            if prediction.confidence is None:
                return await log_no_action(
                    symbol=symbol,
                    reason=prediction.confidence_unavailable_reason
                    or "Confidence unavailable for this model.",
                    predicted_value=prediction.predicted_value,
                    prediction_id=prediction_id,
                )

            confidence_pct = Decimal(str(prediction.confidence)) * Decimal(100)
            if confidence_pct < confidence_threshold_pct:
                return await log_no_action(
                    symbol=symbol,
                    reason=f"Confidence {confidence_pct:.2f}% is below the "
                    f"{confidence_threshold_pct}% threshold.",
                    predicted_value=prediction.predicted_value,
                    confidence=prediction.confidence,
                    prediction_id=prediction_id,
                )

            signal = _interpret_signal(prediction.predicted_value)
            position = await PaperPositionRepository(session).get_by_account_and_symbol(
                account.id, symbol
            )
            held = Decimal(position.quantity) if position is not None else Decimal(0)

            if signal is None:
                return await log_no_action(
                    symbol=symbol,
                    reason=f"Prediction {prediction.predicted_value!r} is not a directional "
                    "up/down call.",
                    predicted_value=prediction.predicted_value,
                    confidence=prediction.confidence,
                    prediction_id=prediction_id,
                )

            trading_service = _build_trading_service(
                session, self._state_manager, settings=settings
            )

            if signal == "up" and held <= 0:
                return await self._open_position(
                    session=session,
                    trading_service=trading_service,
                    decision_repository=decision_repository,
                    account=account,
                    job_id=job_id,
                    symbol=symbol,
                    prediction=prediction,
                    confidence_threshold_pct=confidence_threshold_pct,
                )
            if signal == "down" and held > 0:
                return await self._close_position(
                    trading_service=trading_service,
                    decision_repository=decision_repository,
                    account=account,
                    job_id=job_id,
                    symbol=symbol,
                    held=held,
                    prediction=prediction,
                    confidence_threshold_pct=confidence_threshold_pct,
                )

            if signal == "up":
                reason = "Signal is 'up' but the account is already long — no change to make."
            else:
                reason = (
                    "Signal is 'down' but the account is flat — this platform is long-only, so "
                    "there is nothing to close and no short is ever opened."
                )
            return await log_no_action(
                symbol=symbol,
                reason=reason,
                predicted_value=prediction.predicted_value,
                confidence=prediction.confidence,
                prediction_id=prediction_id,
            )
        except Exception:  # noqa: BLE001 - isolated per account, never stops the rest of the tick
            logger.exception("Paper trading strategy cycle crashed for account=%s", account.id)
            return "no_action"

    async def _open_position(
        self,
        *,
        session: AsyncSession,
        trading_service: PaperTradingService,
        decision_repository: PaperStrategyDecisionRepository,
        account: PaperAccount,
        job_id: uuid.UUID,
        symbol: str,
        prediction: PredictionResponse,
        confidence_threshold_pct: Decimal,
    ) -> str:
        prediction_id = uuid.UUID(prediction.id)
        market = await MarketRepository(session).get_by_symbol(symbol)
        if market is None:
            reason = f"Market {symbol!r} not found."
        else:
            try:
                quote = await resolve_current_price(
                    state_manager=self._state_manager,
                    candle_repository=CandleRepository(session),
                    market_id=market.id,
                    symbol=symbol,
                    staleness_threshold=trading_service.staleness_threshold,
                )
            except NoPriceAvailableError as exc:
                reason = str(exc)
            else:
                balance = Decimal(account.balance)
                target_pct = Decimal(account.max_position_size_pct) * _TARGET_POSITION_SIZE_FRACTION
                quantity = (balance * target_pct / Decimal(100)) / quote.price
                if quantity <= 0:
                    reason = "Balance too small to size a new automated position."
                else:
                    stop_loss_pct = Decimal(account.strategy_default_stop_loss_pct)
                    stop_loss_price = quote.price * (Decimal(1) - stop_loss_pct / Decimal(100))
                    try:
                        order = await trading_service.place_order(
                            account.id,
                            PaperOrderRequest(
                                symbol=symbol,
                                side="buy",
                                quantity=quantity,
                                stop_loss_price=stop_loss_price,
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001 - rejection is a logged no_action
                        reason = f"Automated buy rejected: {exc}"
                    else:
                        await decision_repository.create(
                            _build_decision(
                                account_id=account.id,
                                training_job_id=job_id,
                                symbol=symbol,
                                action="opened",
                                reason=f"Confidence {prediction.confidence:.2%} >= "
                                f"{confidence_threshold_pct}% threshold; signal 'up' while flat — "
                                f"opened {quantity} {symbol} with a stop-loss at "
                                f"{stop_loss_price}.",
                                predicted_value=prediction.predicted_value,
                                confidence=prediction.confidence,
                                confidence_threshold_pct=confidence_threshold_pct,
                                prediction_id=prediction_id,
                                order_id=uuid.UUID(order.id),
                            )
                        )
                        return "opened"

        await decision_repository.create(
            _build_decision(
                account_id=account.id,
                training_job_id=job_id,
                symbol=symbol,
                action="no_action",
                reason=reason[:500],
                predicted_value=prediction.predicted_value,
                confidence=prediction.confidence,
                confidence_threshold_pct=confidence_threshold_pct,
                prediction_id=prediction_id,
                order_id=None,
            )
        )
        return "no_action"

    async def _close_position(
        self,
        *,
        trading_service: PaperTradingService,
        decision_repository: PaperStrategyDecisionRepository,
        account: PaperAccount,
        job_id: uuid.UUID,
        symbol: str,
        held: Decimal,
        prediction: PredictionResponse,
        confidence_threshold_pct: Decimal,
    ) -> str:
        prediction_id = uuid.UUID(prediction.id)
        try:
            order = await trading_service.place_order(
                account.id, PaperOrderRequest(symbol=symbol, side="sell", quantity=held)
            )
        except Exception as exc:  # noqa: BLE001 - rejection is a logged no_action
            await decision_repository.create(
                _build_decision(
                    account_id=account.id,
                    training_job_id=job_id,
                    symbol=symbol,
                    action="no_action",
                    reason=f"Automated close rejected: {exc}"[:500],
                    predicted_value=prediction.predicted_value,
                    confidence=prediction.confidence,
                    confidence_threshold_pct=confidence_threshold_pct,
                    prediction_id=prediction_id,
                    order_id=None,
                )
            )
            return "no_action"

        await decision_repository.create(
            _build_decision(
                account_id=account.id,
                training_job_id=job_id,
                symbol=symbol,
                action="closed",
                reason=f"Confidence {prediction.confidence:.2%} >= {confidence_threshold_pct}% "
                f"threshold; signal 'down' while long — closed {held} {symbol}.",
                predicted_value=prediction.predicted_value,
                confidence=prediction.confidence,
                confidence_threshold_pct=confidence_threshold_pct,
                prediction_id=prediction_id,
                order_id=uuid.UUID(order.id),
            )
        )
        return "closed"


def _interpret_signal(predicted_value: object) -> str | None:
    """`"up"`/`"down"` map to a directional signal; anything else
    (`"flat"`, a regressor's own number, an unexpected label) is not one —
    the strategy only ever acts on an explicit up/down call."""
    if predicted_value == "up":
        return "up"
    if predicted_value == "down":
        return "down"
    return None


def _build_trading_service(
    session: AsyncSession, state_manager: MarketStateManager, *, settings: Settings
) -> PaperTradingService:
    """Build a `PaperTradingService` bound to this tick's own session —
    mirrors `app.dependencies.paper_trading.get_paper_trading_service`
    exactly (same settings, same repositories), just without the FastAPI
    `Depends` wrapper, since there is no request here (the identical
    reason `StopLossTakeProfitMonitor` builds its own copy the same way).
    """
    return PaperTradingService(
        account_repository=PaperAccountRepository(session),
        order_repository=PaperOrderRepository(session),
        position_repository=PaperPositionRepository(session),
        market_repository=MarketRepository(session),
        candle_repository=CandleRepository(session),
        training_job_repository=TrainingJobRepository(session),
        strategy_decision_repository=PaperStrategyDecisionRepository(session),
        state_manager=state_manager,
        slippage_bps=settings.paper_trading_slippage_bps,
        fee_bps=settings.paper_trading_fee_bps,
        triggered_slippage_bps=settings.paper_trading_triggered_slippage_bps,
        staleness_threshold=timedelta(seconds=settings.paper_trading_stale_price_threshold_seconds),
        default_max_position_size_pct=settings.paper_trading_default_max_position_size_pct,
        default_max_exposure_pct=settings.paper_trading_default_max_exposure_pct,
        default_max_drawdown_pct=settings.paper_trading_default_max_drawdown_pct,
        max_order_attempts=settings.paper_trading_max_order_attempts,
        default_strategy_confidence_threshold_pct=(
            settings.paper_trading_strategy_default_confidence_threshold_pct
        ),
        default_strategy_default_stop_loss_pct=(
            settings.paper_trading_strategy_default_stop_loss_pct
        ),
    )


def _build_decision(
    *,
    account_id: uuid.UUID,
    training_job_id: uuid.UUID | None,
    symbol: str | None,
    action: str,
    reason: str,
    predicted_value: object | None,
    confidence: float | None,
    confidence_threshold_pct: Decimal,
    prediction_id: uuid.UUID | None,
    order_id: uuid.UUID | None,
) -> PaperStrategyDecision:
    return PaperStrategyDecision(
        account_id=account_id,
        training_job_id=training_job_id,
        symbol=symbol,
        action=action,
        reason=reason,
        predicted_value=predicted_value,
        confidence=confidence,
        confidence_threshold_pct=confidence_threshold_pct,
        prediction_id=prediction_id,
        order_id=order_id,
    )


async def run_strategy_once() -> StrategyTickSummary:
    """Run one strategy pass synchronously (ops and manual verification).

    Builds its own, throwaway `MarketStateManager` — unlike
    `run_sync_once`/`run_grading_once`, this scheduler's own tick needs a
    *live* price to size and stop-loss a new automated buy, which an
    empty, unattached state manager never has; a manual invocation of
    this entry point falls back to the same stored-candle-close path
    `resolve_current_price` already offers when no live ticker/trade is
    flowing (see that function's own docstring) — it is never left
    unable to act just because this convenience entry point didn't wire
    up the process-wide bus.
    """
    scheduler = PaperTradingStrategyScheduler(state_manager=MarketStateManager())
    summary = await scheduler.run_strategy_tick()
    logger.info(
        "Paper trading strategy run completed: opened=%d closed=%d no_action=%d in %.2fs",
        summary.opened,
        summary.closed,
        summary.no_action,
        summary.duration_seconds,
    )
    return summary
