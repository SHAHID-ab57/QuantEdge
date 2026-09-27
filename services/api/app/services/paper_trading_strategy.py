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
4. Interpret `predicted_value`: `"up"` is bullish (a long), `"down"` is
   bearish (a short), anything else (`"flat"`, a regressor's own number, ...)
   is not a directional call — logged `no_action`. Then, by what the account
   holds in that market:

   | call   | flat                | long held             | short held            |
   | ------ | ------------------- | --------------------- | --------------------- |
   | `up`   | **open a long**     | no change (`no_action`) | **close the short**   |
   | `down` | **open a short**    | **close the long**    | no change (`no_action`) |

   One action per cycle: a reversal closes this cycle and, if the call still
   stands, opens the other side on a later cycle, so no order is ever
   larger than the position it reduces. An entry is sized at half the
   account's own `max_position_size_pct` of its cash (notional; deliberately
   conservative headroom for slippage/fee and any other open exposure, since
   there is no separate strategy-specific sizing config), is placed at the
   account's **fixed `strategy_leverage`**, and carries a **mandatory
   stop-loss** at `strategy_default_stop_loss_pct` on the losing side of the
   resolved price (below a long's, above a short's; `place_order`'s own
   `InvalidStopLossPriceError`/`StopBeyondLiquidationError` are the backstop if
   the price has moved by fill time, itself logged `no_action` rather than
   raised). A close is a `reduce_only` order, so one that loses a race to a
   stop-loss or a liquidation fails instead of opening the opposite side.

**Leverage is fixed, and is never derived from the prediction.** The one
number is `PaperAccount.strategy_leverage` (default 2, tunable per account).
Nothing in this module reads a prediction's confidence into it, and
`PaperTradingService` refuses an automated entry at any other leverage. That is
a deliberate decision, not an omission: the model's confidence has been
measured to carry no reliable relationship to being right (mean confidence 0.889
against accuracy 0.460 over 8,126 graded predictions, correlation -0.020), so
scaling leverage by it would put the largest bets on the least trustworthy
signal. Confidence only decides *whether* to act, through the threshold.

**Disclosed consequence.** The live model calls "down" in 99.8%+ of cases
across every regime tested, so with shorts enabled this strategy will very
likely be almost always short. That is the model's own measured behaviour
becoming visible, not something this module introduces; the decision log shows
each cycle's direction so it can be seen and audited.

**Stop-loss width, position size, and leverage can all be volatility-scaled,
but direction never is (VOLATILITY-STOP-WIDTH "Option B" + VOLATILITY-
POSITION-SIZING "Option A").** An account may optionally set
`PaperAccount.strategy_volatility_training_job_id` to a *second*,
`logistic_regression`-trained job — a distinct model lineage from the one
above that decides direction — whose fresh `volatility_regime` forecast for
the same symbol scales, together, on a new entry: `strategy_default_stop_loss_pct`
(wider ahead of "expand", tighter ahead of "contract"), the target position
size, and `strategy_leverage` (smaller ahead of "expand", larger — never past
the account's own `max_position_size_pct`/`max_leverage`, never touching
`max_exposure_pct` — ahead of "contract"), all three from one shared forecast
fetch (`_resolve_volatility_adjustment`, called only from `_open_position`).
This is **at position-open time only** — it never touches which side is
opened (that stays exactly as decided above, unconditionally), and it never
revisits an already-open position's stop/size/leverage on a later tick;
refreshing one is a possible future extension, not built here, matching
this feature's own smaller-blast-radius scope
(`docs/research/VOLATILITY_RISK_SIZING_DESIGN.md`). Every gate is
fail-closed to the unscaled defaults — wrong model lineage, wrong symbol, no
forecast, or the forecast's own inputs reported drifted all fall back rather
than guess or continue on a reading that can't be trusted
(`_resolve_volatility_adjustment`'s own docstring has the full list). The
resulting stop-loss price and leverage are still passed through the
identical `trading_service.place_order` call as every other automated
entry, so a stop is still rejected exactly as before if it would sit beyond
the position's own liquidation price, and a leverage value is still checked
against `max_leverage` exactly as before (`place_order`'s own
`expected_leverage` parameter carries the scaled value through
`_enforce_automated_restrictions` rather than assuming the account's raw
`strategy_leverage`). Unset (`None`, the default for every existing
account) behaves exactly as before either feature existed. Never applies to
a manual order — this module is the only caller that can ever set an
automated entry's stop-loss, size, or leverage from a forecast at all.

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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.engine import get_engine
from app.dependencies.prediction import get_prediction_service
from app.models.paper_trading import PaperAccount, PaperStrategyDecision
from app.monitoring.error_tracking import capture_feature_drift
from app.paper_trading.errors import NoPriceAvailableError
from app.paper_trading.pricing import resolve_current_price
from app.prediction.feature_drift import DRIFT_Z_THRESHOLD
from app.repositories.audit_log import AuditLogRepository
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

#: VOLATILITY-STOP-WIDTH (Option B): fixed, documented multipliers applied
#: to `strategy_default_stop_loss_pct` when the account's own configured
#: `logistic_regression` volatility job forecasts a regime change for the
#: symbol being traded, and that forecast is neither drift-gated nor
#: unavailable — see `PaperTradingStrategyScheduler._resolve_volatility_adjustment`.
#: `volatility_regime`'s own label is binary (will realized volatility
#: expand or contract relative to the trailing window, with no magnitude),
#: so the response is a modest, asymmetric adjustment — more protective
#: headroom ahead of an expansion than eagerness to tighten ahead of a
#: contraction. **Grounded in real data (VOLATILITY-MULTIPLIER-CHECK)**:
#: replaying this target's own trailing/forward realized-volatility ratio
#: over every labeled row of real ETHUSD/1h and BTCUSD/1h history gives an
#: "expand" ratio (forward_vol/trailing_vol) of median ~1.40-1.42 (IQR
#: ~1.17-1.83) and a "contract" ratio of median ~0.70-0.71 (IQR
#: ~0.54-0.86) on both symbols — ×1.5/×0.75 sit inside both IQRs, close to
#: but slightly more conservative than the raw median, and are confirmed
#: reasonable rather than replaced (see `ARCHITECTURE.md` § "Volatility-
#: Scaled Stop-Loss Width" for the full distribution and symbol-by-symbol
#: numbers). The spread is real, not narrow — a single fixed multiplier is
#: a simplification a future, forecast-magnitude-aware version of this
#: feature could improve on. Applied only to a new automated entry's own
#: stop-loss; a manual order's own human-supplied stop-loss is never
#: touched, and every resulting price still passes through the exact same
#: liquidation-distance check `place_order` already enforces on every
#: stop, scaled or not.
_VOLATILITY_WIDEN_FACTOR = Decimal("1.5")
_VOLATILITY_TIGHTEN_FACTOR = Decimal("0.75")

#: VOLATILITY-POSITION-SIZING (Option A): position-size/leverage scaling
#: from the same forecast Option B already scales stop-loss width from —
#: shrink both ahead of an "expand" forecast, grow both (capped by the
#: account's own existing `max_position_size_pct`/`max_leverage` — never
#: `max_exposure_pct`) ahead of a "contract" forecast. Deliberately the
#: *exact reciprocal* of Option B's own already-validated multipliers
#: (VOLATILITY-MULTIPLIER-CHECK: expand ratio median ~1.40-1.42, contract
#: ratio median ~0.70-0.71 on real ETHUSD/1h and BTCUSD/1h history) rather
#: than a second, independently-chosen pair of constants — one coherent
#: model: if the stop needs to be W times wider to accommodate the
#: forecast range, sizing down by 1/W keeps the expected dollar-risk on a
#: stop-out roughly constant instead of widening it right when volatility
#: is already forecast to expand. Exact fractions (2/3, 4/3), not decimal
#: approximations of 1/1.5 and 1/0.75.
_VOLATILITY_SIZE_SHRINK_FACTOR = Decimal(2) / Decimal(3)
_VOLATILITY_SIZE_GROW_FACTOR = Decimal(4) / Decimal(3)


@dataclass(frozen=True)
class VolatilityAdjustment:
    """The stop-loss width, target position-size fraction, and leverage a
    new automated entry should actually use this cycle — `default_*`
    values unchanged when no scaling applies (no volatility job
    configured, or any of `_resolve_volatility_adjustment`'s own fail-closed
    gates triggered), scaled together from one shared forecast fetch
    otherwise. `note` is an already `f"..."`-ready clause appended verbatim
    to the decision-log reason, empty when unscaled."""

    stop_loss_pct: Decimal
    target_pct: Decimal
    leverage: Decimal
    note: str


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
        # Snapshotted once for the whole cycle: what is logged is what was in
        # force, never re-read from a since-changed account.
        strategy_leverage = Decimal(account.strategy_leverage)
        # Read up front: a rollback (the crash path below) expires the row, and
        # a lazy reload of `account.id` in async code would raise.
        account_id = account.id

        async def log_no_action(
            *,
            symbol: str | None = None,
            reason: str,
            predicted_value: object | None = None,
            confidence: float | None = None,
            prediction_id: uuid.UUID | None = None,
            direction: str | None = None,
        ) -> str:
            await decision_repository.create(
                _build_decision(
                    account_id=account_id,
                    training_job_id=job_id,
                    symbol=symbol,
                    action="no_action",
                    reason=reason[:500],
                    predicted_value=predicted_value,
                    confidence=confidence,
                    confidence_threshold_pct=confidence_threshold_pct,
                    prediction_id=prediction_id,
                    order_id=None,
                    direction=direction,
                    strategy_leverage=strategy_leverage,
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

            # Checked before every other gate, including confidence: a
            # feature-drifted model's saturated confidence is exactly the
            # failure mode this guards against (both real incidents behind
            # this check were >99% confident "down" — see
            # docs/research/FEATURE_DRIFT_INVESTIGATION.md), so a drifted
            # prediction must never reach the confidence/signal logic below
            # at all, however confident it claims to be.
            if prediction.feature_drift_status == "drifted":
                # `compute_feature_drift`'s own contract: `worst_feature`/`worst_z` are set
                # whenever status is "drifted" — never both None together.
                assert prediction.feature_drift_worst_feature is not None
                assert prediction.feature_drift_worst_z is not None
                await _pause_for_drift(
                    session,
                    account,
                    training_job_id=job_id,
                    worst_feature=prediction.feature_drift_worst_feature,
                    worst_z=prediction.feature_drift_worst_z,
                )
                return await log_no_action(
                    symbol=symbol,
                    reason=(
                        f"Auto-paused: feature drift detected "
                        f"({prediction.feature_drift_worst_feature} "
                        f"z={prediction.feature_drift_worst_z:.2f}, "
                        f"threshold {DRIFT_Z_THRESHOLD:.1f}). Strategy disabled; "
                        "re-enable via PATCH .../strategy once reviewed."
                    ),
                    predicted_value=prediction.predicted_value,
                    confidence=prediction.confidence,
                    prediction_id=prediction_id,
                )

            # The side the model's call points at, known before any gate, so
            # even a cycle skipped for low confidence records what it was
            # skipped *for*. ("up" is a long, "down" is a short.) Confidence
            # is used below for exactly one thing: whether to act at all.
            signal = _interpret_signal(prediction.predicted_value)
            call_direction = None if signal is None else ("long" if signal == "up" else "short")
            if prediction.confidence is None:
                return await log_no_action(
                    symbol=symbol,
                    reason=prediction.confidence_unavailable_reason
                    or "Confidence unavailable for this model.",
                    predicted_value=prediction.predicted_value,
                    prediction_id=prediction_id,
                    direction=call_direction,
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
                    direction=call_direction,
                )

            position = await PaperPositionRepository(session).get_by_account_and_symbol(
                account.id, symbol
            )
            held = Decimal(position.quantity) if position is not None else Decimal(0)
            held_side = position.side if position is not None and held > 0 else None

            if signal is None:
                return await log_no_action(
                    symbol=symbol,
                    reason=f"Prediction {prediction.predicted_value!r} is not a directional "
                    "up/down call.",
                    predicted_value=prediction.predicted_value,
                    confidence=prediction.confidence,
                    prediction_id=prediction_id,
                )

            assert call_direction is not None  # `signal` is not None past the check above

            trading_service = _build_trading_service(
                session, self._state_manager, settings=settings
            )

            if held_side is None:
                return await self._open_position(
                    session=session,
                    trading_service=trading_service,
                    decision_repository=decision_repository,
                    account=account,
                    job_id=job_id,
                    symbol=symbol,
                    direction=call_direction,
                    prediction=prediction,
                    confidence_threshold_pct=confidence_threshold_pct,
                )
            if held_side != call_direction:
                return await self._close_position(
                    trading_service=trading_service,
                    decision_repository=decision_repository,
                    account=account,
                    job_id=job_id,
                    symbol=symbol,
                    held=held,
                    held_side=held_side,
                    prediction=prediction,
                    confidence_threshold_pct=confidence_threshold_pct,
                )

            return await log_no_action(
                symbol=symbol,
                reason=f"Signal is '{signal}' and the account is already {held_side} — no "
                "change to make.",
                predicted_value=prediction.predicted_value,
                confidence=prediction.confidence,
                prediction_id=prediction_id,
                direction=call_direction,
            )
        except Exception as exc:  # noqa: BLE001 - isolated per account, never stops the rest of the tick
            logger.exception("Paper trading strategy cycle crashed for account=%s", account.id)
            # Every cycle is logged, including one that crashed. The session may
            # be unusable (the failure may have been the database), so this is
            # best-effort and never raises out of the tick.
            with contextlib.suppress(Exception):
                await session.rollback()
                await log_no_action(reason=f"Cycle failed unexpectedly: {exc}")
            return "no_action"

    async def _resolve_volatility_adjustment(
        self,
        *,
        session: AsyncSession,
        account: PaperAccount,
        symbol: str,
        default_stop_loss_pct: Decimal,
        default_target_pct: Decimal,
        max_position_size_pct: Decimal,
        default_leverage: Decimal,
        max_leverage: Decimal,
    ) -> VolatilityAdjustment:
        """A new automated entry's stop-loss width, target position-size
        fraction, and leverage — all three scaled together from one shared
        `volatility_regime` forecast fetch when the account has opted in
        (`strategy_volatility_training_job_id` set), or every `default_*`
        value returned unchanged for every other account, exactly as before
        either feature existed. One fetch, not two: Option A (size/leverage,
        this method) and Option B (stop-loss width, its own prior name) read
        the identical forecast rather than each independently calling the
        prediction service — this cycle's per-account inference/DB cost is
        the same as before Option A existed, not doubled.

        Every gate below is fail-**closed**: any way this can't produce a
        trustworthy forecast for *this* symbol returns every `default_*`
        value unchanged rather than guessing, silently continuing on a
        drifted reading, or raising and losing the entry entirely. This is
        strictly downstream of the direction/whether-to-trade decision
        already made by the caller — it only ever changes what
        `_open_position` computes `quantity`/`stop_loss_price` from and what
        leverage it requests, never whether an order is placed or which side
        it's on (the identical boundary-preserving requirement
        VOLATILITY-STOP-WIDTH already proved; see
        `tests/paper_trading/test_strategy_scheduler.py
        ::TestVolatilityStopWidth::test_direction_and_whether_to_trade_are_unaffected`,
        extended by VOLATILITY-POSITION-SIZING's own equivalent test).

        `target_pct`/`leverage` are each independently bounded by
        `max_position_size_pct`/`max_leverage` when scaled up — the account's
        own existing ceilings, never `max_exposure_pct` itself, exactly
        matching `VOLATILITY_RISK_SIZING_DESIGN.md`'s own explicit
        requirement. `VolatilityAdjustment.note` is an already `f"..."`-ready
        clause appended verbatim to this cycle's own decision-log reason so
        every scaled (or skipped) value is visible in
        `GET .../strategy/decisions`, not just inferable from the fill price
        or the resulting position's own leverage after the fact.
        """
        volatility_job_id = account.strategy_volatility_training_job_id
        unscaled = VolatilityAdjustment(
            stop_loss_pct=default_stop_loss_pct,
            target_pct=default_target_pct,
            leverage=default_leverage,
            note="",
        )
        if volatility_job_id is None:
            return unscaled

        def unscaled_with(note: str) -> VolatilityAdjustment:
            return VolatilityAdjustment(
                stop_loss_pct=default_stop_loss_pct,
                target_pct=default_target_pct,
                leverage=default_leverage,
                note=note,
            )

        job = await TrainingJobRepository(session).get_by_id(volatility_job_id)
        if job is None:
            return unscaled_with(" (volatility job no longer exists — unscaled defaults used)")
        if job.model_type != "logistic_regression":
            return unscaled_with(
                f" (volatility job is {job.model_type!r}, not logistic_regression — unscaled "
                "defaults used)"
            )
        if job.symbol != symbol:
            return unscaled_with(
                f" (volatility job trades {job.symbol!r}, not {symbol!r} — unscaled defaults "
                "used)"
            )

        prediction_service = get_prediction_service(session)
        try:
            forecast = await prediction_service.run(
                PredictionRunRequest(training_job_id=volatility_job_id, symbol=symbol)
            )
        except Exception as exc:  # noqa: BLE001 - a failed forecast falls back, never blocks the entry
            return unscaled_with(
                f" (volatility forecast unavailable ({exc}) — unscaled defaults used)"
            )

        # Checked before the forecast's own value is trusted at all — the
        # exact same posture the directional signal already takes on its own
        # prediction, above, and for the same reason: a drifted model's
        # output is not a reading to act on, however confident it claims to
        # be.
        if forecast.feature_drift_status == "drifted":
            return unscaled_with(
                f" (volatility forecast's own inputs are drifted "
                f"({forecast.feature_drift_worst_feature} "
                f"z={forecast.feature_drift_worst_z:.2f}) — unscaled defaults used)"
            )

        if forecast.predicted_value == "expand":
            return VolatilityAdjustment(
                stop_loss_pct=default_stop_loss_pct * _VOLATILITY_WIDEN_FACTOR,
                target_pct=default_target_pct * _VOLATILITY_SIZE_SHRINK_FACTOR,
                leverage=max(default_leverage * _VOLATILITY_SIZE_SHRINK_FACTOR, Decimal(1)),
                note=" (widened stop / sized down: volatility forecast 'expand')",
            )
        if forecast.predicted_value == "contract":
            scaled_leverage = min(default_leverage * _VOLATILITY_SIZE_GROW_FACTOR, max_leverage)
            note = " (tightened stop / sized up: volatility forecast 'contract'"
            # D1's own already-named cost asymmetry (VOLATILITY_RISK_SIZING_DESIGN.md
            # Step 3): leverage amplifies the fixed ~0.30%-of-notional round-trip
            # cost as much as it amplifies exposure, so scaling it up is logged
            # plainly, not left implicit in a bare leverage number.
            if scaled_leverage > default_leverage:
                note += (
                    f"; leverage {default_leverage}x -> {scaled_leverage}x increases the fixed "
                    "round-trip transaction cost on trades taken during this window"
                )
            note += ")"
            return VolatilityAdjustment(
                stop_loss_pct=default_stop_loss_pct * _VOLATILITY_TIGHTEN_FACTOR,
                target_pct=min(
                    default_target_pct * _VOLATILITY_SIZE_GROW_FACTOR, max_position_size_pct
                ),
                leverage=scaled_leverage,
                note=note,
            )
        return unscaled_with(
            f" (volatility job predicted {forecast.predicted_value!r}, not an expand/contract "
            "call — unscaled defaults used)"
        )

    async def _open_position(
        self,
        *,
        session: AsyncSession,
        trading_service: PaperTradingService,
        decision_repository: PaperStrategyDecisionRepository,
        account: PaperAccount,
        job_id: uuid.UUID,
        symbol: str,
        direction: str,
        prediction: PredictionResponse,
        confidence_threshold_pct: Decimal,
    ) -> str:
        """Open a long (`direction="long"`, a buy) or a short (`"short"`, a
        sell) at the account's fixed `strategy_leverage` (or a
        volatility-scaled variant of it, VOLATILITY-POSITION-SIZING), with a
        mandatory stop-loss on the losing side of the resolved price."""
        prediction_id = uuid.UUID(prediction.id)
        # The account's own raw, human-set configuration -- snapshotted for
        # the decision log exactly as every other field on it already is
        # (`PaperStrategyDecision.strategy_leverage`'s own docstring: "never
        # re-read from the possibly-since-changed account"), independent of
        # whatever leverage this specific cycle actually trades at.
        strategy_leverage = Decimal(account.strategy_leverage)
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
                max_position_size_pct = Decimal(account.max_position_size_pct)
                default_target_pct = max_position_size_pct * _TARGET_POSITION_SIZE_FRACTION
                default_stop_loss_pct = Decimal(account.strategy_default_stop_loss_pct) / (
                    Decimal(100)
                )
                adjustment = await self._resolve_volatility_adjustment(
                    session=session,
                    account=account,
                    symbol=symbol,
                    default_stop_loss_pct=default_stop_loss_pct,
                    default_target_pct=default_target_pct,
                    max_position_size_pct=max_position_size_pct,
                    default_leverage=strategy_leverage,
                    max_leverage=Decimal(account.max_leverage),
                )
                quantity = (balance * adjustment.target_pct / Decimal(100)) / quote.price
                if quantity <= 0:
                    reason = "Balance too small to size a new automated position."
                else:
                    # Mandatory, and on the losing side: below a long's entry,
                    # above a short's.
                    stop_loss_price = quote.price * (
                        Decimal(1) - adjustment.stop_loss_pct
                        if direction == "long"
                        else Decimal(1) + adjustment.stop_loss_pct
                    )
                    try:
                        order = await trading_service.place_order(
                            account.id,
                            PaperOrderRequest(
                                symbol=symbol,
                                side="buy" if direction == "long" else "sell",
                                quantity=quantity,
                                leverage=adjustment.leverage,
                                stop_loss_price=stop_loss_price,
                            ),
                            automated=True,
                            expected_leverage=adjustment.leverage,
                        )
                    except Exception as exc:  # noqa: BLE001 - rejection is a logged no_action
                        reason = f"Automated {direction} entry rejected: {exc}"
                    else:
                        await decision_repository.create(
                            _build_decision(
                                account_id=account.id,
                                training_job_id=job_id,
                                symbol=symbol,
                                action="opened",
                                reason=f"Confidence {prediction.confidence:.2%} >= "
                                f"{confidence_threshold_pct}% threshold; signal "
                                f"'{prediction.predicted_value}' while flat — opened a "
                                f"{direction} of {quantity} {symbol} at {adjustment.leverage}x "
                                f"leverage with a stop-loss at {stop_loss_price}"
                                f"{adjustment.note}.",
                                predicted_value=prediction.predicted_value,
                                confidence=prediction.confidence,
                                confidence_threshold_pct=confidence_threshold_pct,
                                prediction_id=prediction_id,
                                order_id=uuid.UUID(order.id),
                                direction=direction,
                                strategy_leverage=strategy_leverage,
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
                direction=direction,
                strategy_leverage=strategy_leverage,
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
        held_side: str,
        prediction: PredictionResponse,
        confidence_threshold_pct: Decimal,
    ) -> str:
        """Close the whole held position (a sell for a long, a buy for a short),
        `reduce_only` so that if something else has already closed it (a
        stop-loss, a liquidation) this fails instead of opening the opposite
        side."""
        prediction_id = uuid.UUID(prediction.id)
        strategy_leverage = Decimal(account.strategy_leverage)
        try:
            order = await trading_service.place_order(
                account.id,
                PaperOrderRequest(
                    symbol=symbol,
                    side="sell" if held_side == "long" else "buy",
                    quantity=held,
                    reduce_only=True,
                ),
                automated=True,
            )
        except Exception as exc:  # noqa: BLE001 - rejection is a logged no_action
            await decision_repository.create(
                _build_decision(
                    account_id=account.id,
                    training_job_id=job_id,
                    symbol=symbol,
                    action="no_action",
                    reason=f"Automated close of the {held_side} rejected: {exc}"[:500],
                    predicted_value=prediction.predicted_value,
                    confidence=prediction.confidence,
                    confidence_threshold_pct=confidence_threshold_pct,
                    prediction_id=prediction_id,
                    order_id=None,
                    direction=held_side,
                    strategy_leverage=strategy_leverage,
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
                f"threshold; signal '{prediction.predicted_value}' while {held_side} — closed "
                f"{held} {symbol}.",
                predicted_value=prediction.predicted_value,
                confidence=prediction.confidence,
                confidence_threshold_pct=confidence_threshold_pct,
                prediction_id=prediction_id,
                order_id=uuid.UUID(order.id),
                direction=held_side,
                strategy_leverage=strategy_leverage,
            )
        )
        return "closed"


async def _pause_for_drift(
    session: AsyncSession,
    account: PaperAccount,
    *,
    training_job_id: uuid.UUID,
    worst_feature: str,
    worst_z: float,
) -> None:
    """Disable an account's strategy because its own fresh prediction just
    came back feature-drifted (FEATURE-DRIFT-MONITOR, Option C, "auto-pause"
    — the chosen response policy; see
    `docs/research/FEATURE_DRIFT_INVESTIGATION.md`).

    Deliberately **not** routed through `PaperTradingService
    .update_strategy_config` (the human-facing `PATCH .../strategy` path):
    that method requires a real `user_id` for its audit-trail write, and
    there is no human here — the same reason a fully-automated state change
    already on this platform, the drawdown kill switch's own
    `PaperTradingService._alert_halted`, writes a structured log line plus a
    Sentry alert and never an `audit_log` row. This mutates the exact same
    `strategy_enabled` field `PATCH .../strategy` controls, through the same
    `PaperAccountRepository.update`, so it is recognizable as the same kind
    of state change even though it reaches the database differently.
    """
    now = datetime.now(UTC)
    await PaperAccountRepository(session).update(
        account,
        {
            "strategy_enabled": False,
            "strategy_paused_reason": "feature_drift",
            "strategy_paused_at": now,
        },
    )
    logger.error(
        "Paper trading strategy auto-paused for account=%s: feature drift detected "
        "(job=%s, %s z=%.2f)",
        account.id,
        training_job_id,
        worst_feature,
        worst_z,
    )
    capture_feature_drift(
        str(account.id),
        training_job_id=str(training_job_id),
        worst_feature=worst_feature,
        worst_z=worst_z,
        threshold=DRIFT_Z_THRESHOLD,
    )


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
        audit_log_repository=AuditLogRepository(session),
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
        default_strategy_leverage=settings.paper_trading_strategy_default_leverage,
        default_max_leverage=settings.paper_trading_default_max_leverage,
        maintenance_margin_rate=settings.paper_trading_maintenance_margin_pct / Decimal(100),
        max_leverage_notional=settings.paper_trading_max_leverage_notional,
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
    direction: str | None,
    strategy_leverage: Decimal,
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
        direction=direction,
        strategy_leverage=strategy_leverage,
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
