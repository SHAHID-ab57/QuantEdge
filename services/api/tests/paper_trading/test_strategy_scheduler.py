"""Tests for `PaperTradingStrategyScheduler` — periodic execution of each
account's own, optional automated strategy.

Mirrors `tests/services/test_grading_scheduler.py`'s own conventions:
`get_engine` monkeypatched to the test's in-memory engine, since this
scheduler never goes through `get_db`/FastAPI's dependency overrides —
there is no request behind a scheduled tick. Most tests below also
monkeypatch the scheduler module's own `get_prediction_service` reference
to a stub returning a specific, controlled `PredictionResponse` — the
strategy's own decision logic (confidence threshold, up/down signal,
flat/long) is a pure orchestration question that doesn't need a real
model's actual, hard-to-control output to exercise every branch
deterministically. `TestRealPredictionWiring` is the one exception: it
uses a genuinely trained job and an unstubbed prediction call, proving
the real wiring (job -> its own recorded symbol -> a fresh prediction)
actually works end to end, the same real-data conviction
`tests/services/test_grading_scheduler.py` itself established for its
own scheduler.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.events.bus import EventBus
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperOrderRequest,
    PaperStrategyConfigUpdateRequest,
)
from app.schemas.prediction import PredictionResponse
from app.services import paper_trading_strategy as strategy_module
from app.services.paper_trading import PaperTradingService
from app.services.paper_trading_strategy import PaperTradingStrategyScheduler, run_strategy_once
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory
from tests.paper_trading.test_service import build_service, publish_ticker, seed_market
from tests.prediction.test_service import train_completed_job


@pytest.fixture(autouse=True)
def _use_test_engine(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr(strategy_module, "get_engine", lambda: engine)


def build_prediction(
    *,
    training_job_id: str,
    symbol: str,
    predicted_value: object,
    confidence: float | None,
) -> PredictionResponse:
    now = datetime.now(UTC)
    return PredictionResponse(
        id=str(uuid.uuid4()),
        training_job_id=training_job_id,
        experiment_id=str(uuid.uuid4()),
        symbol=symbol,
        timeframe="1h",
        model_type="logistic_regression",
        model_kind="classification",
        target_column="next_direction_1",
        horizon=1,
        as_of=now,
        predicted_value=predicted_value,
        confidence=confidence,
        feature_columns=["open", "high", "low", "close", "volume"],
        created_at=now,
    )


class _StubPredictionService:
    """A `PredictionService` stand-in returning (or raising) one fixed
    outcome, regardless of what's actually requested — this module's own
    tests control confidence/predicted_value directly rather than
    depending on a real trained model's actual, harder-to-predict output.
    """

    def __init__(self, outcome: PredictionResponse | Exception) -> None:
        self._outcome = outcome

    async def run(self, request: object) -> PredictionResponse:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def stub_prediction(
    monkeypatch: pytest.MonkeyPatch, outcome: PredictionResponse | Exception
) -> None:
    monkeypatch.setattr(
        strategy_module,
        "get_prediction_service",
        lambda session: _StubPredictionService(outcome),  # noqa: ARG005
    )


class _FreshEachCallPredictionService:
    """Mints a genuinely new `PredictionResponse` — a new `id`, a new
    `created_at` — on every single `.run()` call, while holding
    `predicted_value`/`confidence` fixed. This is the honest simulation
    of "the underlying candle hasn't advanced": the real, unstubbed
    `PredictionService.run()` never caches or looks up an existing row
    (`PredictionRepository.create` is an unconditional `INSERT`, and
    `run()` always builds a brand-new `Prediction(...)` first) — calling
    it twice against the same latest candle recomputes the identical
    feature vector and therefore the identical `predicted_value`/
    `confidence`, but still persists a second, distinct row. A stub that
    returned the *same* `PredictionResponse` object/id across calls would
    misrepresent that — this one doesn't.
    """

    def __init__(
        self, *, training_job_id: str, symbol: str, predicted_value: object, confidence: float
    ) -> None:
        self._training_job_id = training_job_id
        self._symbol = symbol
        self._predicted_value = predicted_value
        self._confidence = confidence
        self.calls = 0
        self.issued_ids: list[str] = []

    async def run(self, request: object) -> PredictionResponse:
        self.calls += 1
        prediction = build_prediction(
            training_job_id=self._training_job_id,
            symbol=self._symbol,
            predicted_value=self._predicted_value,
            confidence=self._confidence,
        )
        self.issued_ids.append(prediction.id)
        return prediction


async def enable_strategy(
    service: PaperTradingService,
    account_id: uuid.UUID,
    job_id: str,
    *,
    confidence_threshold_pct: Decimal = Decimal("50"),
    default_stop_loss_pct: Decimal = Decimal("5"),
) -> None:
    await service.update_strategy_config(
        account_id,
        PaperStrategyConfigUpdateRequest(
            enabled=True,
            training_job_id=uuid.UUID(job_id),
            confidence_threshold_pct=confidence_threshold_pct,
            default_stop_loss_pct=default_stop_loss_pct,
        ),
    )


@pytest.mark.asyncio
class TestAboveThresholdWithAFlatPositionOpensAnOrder:
    async def test_a_confident_up_prediction_with_a_flat_position_opens_a_buy(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATUPUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol="STRATUPUSD", predicted_value="up", confidence=0.9
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.attempted == 1
        assert summary.opened == 1
        assert summary.closed == 0
        assert summary.no_action == 0

        positions = await service.list_positions(uuid.UUID(account.id))
        assert len(positions.positions) == 1
        assert positions.positions[0].symbol == "STRATUPUSD"
        assert positions.positions[0].quantity > 0

        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 1
        assert decisions.decisions[0].action == "opened"
        assert decisions.decisions[0].symbol == "STRATUPUSD"
        assert decisions.decisions[0].predicted_value == "up"
        assert decisions.decisions[0].order_id is not None


@pytest.mark.asyncio
class TestEachCycleRequestsAGenuinelyFreshPrediction:
    async def test_every_tick_calls_the_prediction_service_again_never_a_cached_result(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`run_strategy_tick` never skips calling `PredictionService.run`
        just because a previous cycle already ran one for this account —
        there is no cache/memo anywhere in `_process_account`. Proven by
        counting real calls into the stub across two consecutive ticks."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATFRESHCALLUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)

        # Non-directional signal — every tick is a no_action, isolating
        # this test to call-counting alone.
        fresh_service = _FreshEachCallPredictionService(
            training_job_id=job_id,
            symbol="STRATFRESHCALLUSD",
            predicted_value="flat",
            confidence=0.99,
        )
        monkeypatch.setattr(
            strategy_module, "get_prediction_service", lambda session: fresh_service
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        await scheduler.run_strategy_tick()
        await scheduler.run_strategy_tick()

        assert fresh_service.calls == 2
        assert len(set(fresh_service.issued_ids)) == 2  # two distinct prediction ids, never reused

    async def test_a_repeated_identical_signal_across_two_ticks_never_opens_twice(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scenario the fresh-prediction question is really about:
        the underlying candle hasn't advanced, so the model deterministically
        recomputes the *same* confident 'up' signal on the very next tick —
        a genuinely new `Prediction` row each time (see the test above), not
        a stale/cached one. Nothing here deduplicates by prediction id or
        by `as_of` — what actually prevents a second buy is the ordinary
        flat/long position-consistency check (`_process_account`'s own
        `if signal == "up" and held <= 0`): the second tick sees the
        account is now *long* and treats the repeated bullish signal as
        already consistent, not a fresh reason to buy again."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATREPEATUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id)

        fresh_service = _FreshEachCallPredictionService(
            training_job_id=job_id,
            symbol="STRATREPEATUSD",
            predicted_value="up",
            confidence=0.9,
        )
        monkeypatch.setattr(
            strategy_module, "get_prediction_service", lambda session: fresh_service
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        first = await scheduler.run_strategy_tick()
        second = await scheduler.run_strategy_tick()

        assert fresh_service.calls == 2
        assert len(set(fresh_service.issued_ids)) == 2  # each tick got its own fresh prediction row

        assert first.opened == 1
        assert second.opened == 0
        assert second.no_action == 1

        positions = await service.list_positions(account_id)
        assert len(positions.positions) == 1  # exactly one position, not doubled up

        decisions = await service.list_strategy_decisions(account_id, limit=20, offset=0)
        assert decisions.total == 2
        # Two genuinely distinct prediction ids, each backing exactly one
        # decision — looked up by id rather than by list order/`created_at`,
        # since two ticks run back-to-back in the same test can land in
        # the same timestamp tick, and `created_at DESC` ties are then
        # broken by `id ASC` (a random UUID), not insertion order.
        assert {d.prediction_id for d in decisions.decisions} == set(fresh_service.issued_ids)
        by_prediction_id = {d.prediction_id: d for d in decisions.decisions}
        first_decision = by_prediction_id[fresh_service.issued_ids[0]]
        second_decision = by_prediction_id[fresh_service.issued_ids[1]]
        assert first_decision.action == "opened"
        assert second_decision.action == "no_action"
        assert "already long" in second_decision.reason.lower()


@pytest.mark.asyncio
class TestAllFourPositionConsistencyCases:
    """`_process_account`'s own position-consistency branch has exactly
    four reachable combinations of (flat/long, up/down) — every one of
    them produces an explicit, logged outcome, never a silent fallthrough.
    Two are covered by their own dedicated classes elsewhere
    (`TestAboveThresholdWithAFlatPositionOpensAnOrder` — flat+up opens;
    `TestLongAndBearishClosesThePosition` — long+down closes); the other
    two — both "already consistent, nothing to do" — get their own
    explicit tests here rather than being left to an incidental byproduct
    of some other test."""

    async def test_flat_and_bearish_is_a_no_op_never_a_short(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATFLATDOWNUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATFLATDOWNUSD",
                predicted_value="down",
                confidence=0.9,
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.opened == 0
        assert summary.closed == 0
        assert summary.no_action == 1

        positions = await service.list_positions(account_id)
        assert positions.positions == []  # certainly never a short

        decisions = await service.list_strategy_decisions(account_id, limit=20, offset=0)
        decision = decisions.decisions[0]
        assert decision.action == "no_action"
        assert decision.order_id is None
        assert "flat" in decision.reason.lower()
        assert "no short is ever opened" in decision.reason.lower()

    async def test_long_and_bullish_is_a_no_op_already_consistent(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATLONGUPUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="STRATLONGUPUSD", side="buy", quantity=Decimal("1")),
        )
        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATLONGUPUSD",
                predicted_value="up",
                confidence=0.9,
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.opened == 0  # not a second buy on top of the existing manual position
        assert summary.no_action == 1

        positions = await service.list_positions(account_id)
        assert len(positions.positions) == 1
        assert float(positions.positions[0].quantity) == pytest.approx(1.0)

        decisions = await service.list_strategy_decisions(account_id, limit=20, offset=0)
        decision = decisions.decisions[0]
        assert decision.action == "no_action"
        assert decision.order_id is None
        assert "already long" in decision.reason.lower()


def test_interpret_signal_never_matches_a_numeric_value() -> None:
    """Unit-level defense-in-depth: even if some future model adapter
    ever did report a `confidence` for a regressor (see the class below
    for why that never happens today), `_interpret_signal` itself still
    only matches the literal strings `"up"`/`"down"` — a plain number,
    however it arrived, is never treated as a directional call."""
    assert strategy_module._interpret_signal(1234.56) is None  # noqa: SLF001
    assert strategy_module._interpret_signal(0) is None  # noqa: SLF001
    assert strategy_module._interpret_signal("flat") is None  # noqa: SLF001
    assert strategy_module._interpret_signal("up") == "up"  # noqa: SLF001
    assert strategy_module._interpret_signal("down") == "down"  # noqa: SLF001


@pytest.mark.asyncio
class TestRegressionJobsCanBeConfiguredButNeverAct:
    """A regression job is not blocked from being configured for the
    strategy — `update_strategy_config` only checks the job is completed,
    real-data-trained, and has a recorded symbol; it never inspects
    `model_kind`/`target_column`. But in practice it can never act: per
    `PredictionResponse`'s own docstring, `confidence` is populated only
    for an adapter that supports `predict_proba` ("today: logistic_regression")
    — explicitly `None` for every regressor, always — so a regression
    job's own cycle is rejected at the mandatory-confidence gate, every
    time, before signal interpretation is ever reached. The strategy is
    classification-only in effect, not by an explicit config-time check
    against `model_kind`."""

    async def test_a_regression_job_can_be_enabled_but_every_cycle_is_a_no_op(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory,
            symbol="STRATREGRESSUSD",
            model_type="linear_regression",
            target="next_close",
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)

        # Enabling itself is not rejected for a regression job.
        await enable_strategy(service, account_id, job_id)
        assert (await service.get_account(account_id)).strategy_enabled is True

        # No stubbing here — the real `PredictionService.run`, against a
        # real trained `linear_regression` job, genuinely returns
        # `confidence=None` (never a fabricated one for this test).
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.attempted == 1
        assert summary.opened == 0
        assert summary.closed == 0
        assert summary.no_action == 1

        positions = await service.list_positions(account_id)
        assert positions.positions == []

        decisions = await service.list_strategy_decisions(account_id, limit=20, offset=0)
        decision = decisions.decisions[0]
        assert decision.action == "no_action"
        assert decision.confidence is None
        assert decision.order_id is None
        # A real numeric predicted_value was still recorded on the
        # decision (the cycle got as far as the prediction itself; it
        # just could never act on it) — proving this stopped at the
        # confidence gate, not at some earlier failure.
        assert isinstance(decision.predicted_value, float)


@pytest.mark.asyncio
class TestBelowThresholdResultsInNoOrder:
    async def test_a_below_threshold_prediction_places_no_order_but_is_logged(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATLOWUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service, uuid.UUID(account.id), job_id, confidence_threshold_pct=Decimal("90")
        )
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol="STRATLOWUSD", predicted_value="up", confidence=0.5
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.opened == 0
        assert summary.no_action == 1

        positions = await service.list_positions(uuid.UUID(account.id))
        assert positions.positions == []

        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 1
        decision = decisions.decisions[0]
        assert decision.action == "no_action"
        assert decision.order_id is None
        assert "below" in decision.reason.lower()
        assert "threshold" in decision.reason.lower()


@pytest.mark.asyncio
class TestAutomatedPositionsAlwaysCarryAStopLoss:
    async def test_an_automated_buy_always_attaches_a_stop_loss(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATSLUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service, uuid.UUID(account.id), job_id, default_stop_loss_pct=Decimal("7")
        )
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol="STRATSLUSD", predicted_value="up", confidence=0.9
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        positions = await service.list_positions(uuid.UUID(account.id))
        position = positions.positions[0]
        assert position.stop_loss_price is not None

        orders = await service.list_orders(
            uuid.UUID(account.id), sort="created_at", direction="desc", limit=20, offset=0
        )
        order = orders.orders[0]
        # 7% below the *resolved quote* the buy priced from (raw_price,
        # before slippage) — not the fill price itself, which already
        # differs from raw_price by the modeled slippage.
        expected = float(order.raw_price) * 0.93
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)


@pytest.mark.asyncio
class TestLongAndBearishClosesThePosition:
    async def test_a_confident_down_prediction_while_long_closes_the_position(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATDOWNUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        # Already long, manually — the strategy only ever closes an
        # *existing* position, never opens a short one.
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="STRATDOWNUSD", side="buy", quantity=Decimal("1")),
        )

        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATDOWNUSD",
                predicted_value="down",
                confidence=0.9,
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.closed == 1
        assert summary.opened == 0
        assert summary.no_action == 0

        positions = await service.list_positions(account_id)
        assert positions.positions == []

        decisions = await service.list_strategy_decisions(account_id, limit=20, offset=0)
        assert decisions.total == 1
        decision = decisions.decisions[0]
        assert decision.action == "closed"
        assert decision.order_id is not None

    async def test_a_rejected_automated_close_is_logged_as_no_action(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A halted account rejects a triggered close exactly like a
        manual one — proving the close path also shares the existing
        guard, not a second, unguarded one."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATCLOSEHALTUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=Decimal("100"),
                max_drawdown_pct=Decimal("1"),
            )
        )
        account_id = uuid.UUID(account.id)
        # A single large-enough buy spends more than 1% of balance on its
        # own, which already breaches the account's own 1% drawdown limit
        # (see `PaperTradingService._apply_drawdown_tracking`) — halting
        # it before the strategy ever gets a chance to close anything.
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="STRATCLOSEHALTUSD", side="buy", quantity=Decimal("20")),
        )
        risk = await service.risk_summary(account_id)
        assert risk.trading_halted is True

        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATCLOSEHALTUSD",
                predicted_value="down",
                confidence=0.9,
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.closed == 0
        assert summary.no_action == 1

        decisions = await service.list_strategy_decisions(account_id, limit=20, offset=0)
        decision = decisions.decisions[0]
        assert decision.action == "no_action"
        assert "rejected" in decision.reason.lower()


@pytest.mark.asyncio
class TestSharesExistingRiskLimits:
    async def test_a_strategy_order_that_would_breach_max_exposure_is_rejected(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The strategy is 'just another caller' of `place_order` — proven
        here by configuring a tight `max_exposure_pct`, pre-filling most
        of that budget with an ordinary *manual* buy in a different
        symbol, and showing the automated buy is rejected by the exact
        same `MaxExposureExceededError` a manual order would hit in the
        same situation, never a second, unguarded path."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATRISKUSD", model_type="logistic_regression"
        )
        await seed_market(session_factory, symbol="STRATOTHERUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "STRATOTHERUSD", "1000")

        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=Decimal("100"),
                max_exposure_pct=Decimal("5"),
                max_drawdown_pct=Decimal("100"),
            )
        )
        # A manual position worth ~3% of balance — comfortably inside the
        # 5% exposure cap on its own, leaving little headroom.
        await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="STRATOTHERUSD", side="buy", quantity=Decimal("3")),
        )

        await enable_strategy(service, uuid.UUID(account.id), job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATRISKUSD",
                predicted_value="up",
                confidence=0.9,
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.opened == 0
        assert summary.no_action == 1

        positions = await service.list_positions(uuid.UUID(account.id))
        assert {p.symbol for p in positions.positions} == {"STRATOTHERUSD"}

        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        decision = decisions.decisions[0]
        assert decision.action == "no_action"
        assert decision.order_id is None
        assert "rejected" in decision.reason.lower()
        assert "exposure" in decision.reason.lower()


@pytest.mark.asyncio
class TestDisablingStopsFutureCycles:
    async def test_disabling_the_strategy_prevents_the_next_tick_from_acting(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATOFFUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol="STRATOFFUSD", predicted_value="up", confidence=0.9
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        first = await scheduler.run_strategy_tick()
        assert first.attempted == 1
        assert first.opened == 1

        await service.update_strategy_config(
            uuid.UUID(account.id), PaperStrategyConfigUpdateRequest(enabled=False)
        )

        second = await scheduler.run_strategy_tick()
        assert second.attempted == 0
        assert second.opened == 0

        # Only the first tick's decision was ever logged — the disabled
        # account is simply absent from the second tick's own query.
        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 1

    async def test_disabling_mid_cycle_does_not_abort_an_already_in_flight_tick(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`run_strategy_tick` reads `strategy_enabled` exactly once, at
        the top of the tick (`list_strategy_enabled`) — `_process_account`
        never re-checks it afterward, and `place_order` itself has no
        concept of `strategy_enabled` at all (only `trading_halted`, which
        is a different flag). So a disable landing *after* an account was
        already selected into this tick's own batch, but *before* that
        account's own order is placed, does not stop the order: this test
        disables the account from inside the stubbed prediction call
        itself — the exact midpoint between "account selected for this
        tick" and "order placed" — and shows the buy still completes.
        "Disabling takes effect before the next cycle" is therefore a
        tick-boundary guarantee, not a mid-tick one; this is disclosed
        as such in `ARCHITECTURE.md` § "Paper Trading" → "Automated
        Strategy"."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATMIDCYCLEUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id)

        prediction = build_prediction(
            training_job_id=job_id, symbol="STRATMIDCYCLEUSD", predicted_value="up", confidence=0.9
        )

        class _DisableMidCyclePredictionService:
            async def run(self, request: object) -> PredictionResponse:
                # Simulates a concurrent PATCH .../strategy landing here —
                # after this account was already read into the current
                # tick's batch, but before place_order is ever called.
                await service.update_strategy_config(
                    account_id, PaperStrategyConfigUpdateRequest(enabled=False)
                )
                return prediction

        monkeypatch.setattr(
            strategy_module,
            "get_prediction_service",
            lambda session: _DisableMidCyclePredictionService(),  # noqa: ARG005
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        # The in-flight cycle still completed its order...
        assert summary.opened == 1
        positions = await service.list_positions(account_id)
        assert len(positions.positions) == 1

        # ...even though the account is already disabled by the time the
        # tick returns.
        refreshed = await service.get_account(account_id)
        assert refreshed.strategy_enabled is False

        # And the *next* tick is unaffected by it, exactly as
        # TestDisablingStopsFutureCycles proves in the ordinary,
        # non-racing case.
        second = await scheduler.run_strategy_tick()
        assert second.attempted == 0


@pytest.mark.asyncio
class TestEveryCycleIsLogged:
    async def test_every_tick_is_logged_whether_it_acted_or_not(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATLOGUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service, uuid.UUID(account.id), job_id, confidence_threshold_pct=Decimal("80")
        )
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)

        # Tick 1: below threshold — no order, but still logged.
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol="STRATLOGUSD", predicted_value="up", confidence=0.5
            ),
        )
        first = await scheduler.run_strategy_tick()
        assert first.no_action == 1

        # Tick 2: above threshold — opens, and is logged too.
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol="STRATLOGUSD", predicted_value="up", confidence=0.9
            ),
        )
        second = await scheduler.run_strategy_tick()
        assert second.opened == 1

        # Tick 3: signal is 'flat' (not directional) — no order, logged.
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATLOGUSD",
                predicted_value="flat",
                confidence=0.95,
            ),
        )
        third = await scheduler.run_strategy_tick()
        assert third.no_action == 1

        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 3
        actions = {d.action for d in decisions.decisions}
        assert actions == {"no_action", "opened"}


@pytest.mark.asyncio
class TestStartStop:
    async def test_start_noops_without_an_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(strategy_module, "get_engine", lambda: None)
        scheduler = PaperTradingStrategyScheduler(state_manager=MarketStateManager())
        await scheduler.start()
        assert not scheduler.running
        await scheduler.stop()

    async def test_starting_twice_does_not_create_a_second_task(self) -> None:
        scheduler = PaperTradingStrategyScheduler(
            state_manager=MarketStateManager(), interval_seconds=60
        )
        await scheduler.start()
        first_task = scheduler._task  # noqa: SLF001 - white-box: proving no second task
        await scheduler.start()
        assert scheduler._task is first_task  # noqa: SLF001
        await scheduler.stop()
        assert not scheduler.running


@pytest.mark.asyncio
class TestRealPredictionWiring:
    async def test_run_strategy_once_requests_a_real_fresh_prediction_end_to_end(
        self, session_factory: SessionFactory
    ) -> None:
        """No stubbing here — proves the scheduler really resolves the
        account's own `strategy_training_job_id` down to that job's own
        recorded `symbol`, calls the real `PredictionService.run`, and
        logs exactly one decision from the outcome, whatever it is."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATREALUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.attempted == 1
        assert summary.opened + summary.closed + summary.no_action == 1

        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 1
        decision = decisions.decisions[0]
        assert decision.symbol == "STRATREALUSD"
        assert decision.training_job_id == job_id
        if decision.confidence is not None:
            assert 0.0 <= decision.confidence <= 1.0

    async def test_run_strategy_once_runs_a_single_tick(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATONCEUSD", model_type="logistic_regression"
        )
        service = build_service(session_factory, MarketStateManager())
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)

        summary = await run_strategy_once()

        assert summary.attempted == 1
        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 1
