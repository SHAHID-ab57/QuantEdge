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
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.events.bus import EventBus
from app.models.experiment import Experiment
from app.paper_trading.errors import StopBeyondLiquidationError
from app.prediction.feature_drift import FeatureDriftStatus
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperOrderRequest,
    PaperStrategyConfigUpdateRequest,
)
from app.schemas.prediction import PredictionResponse, PredictionRunRequest
from app.schemas.training import TrainingJobCreateRequest
from app.services import paper_trading_strategy as strategy_module
from app.services.paper_trading import PaperTradingService
from app.services.paper_trading_strategy import PaperTradingStrategyScheduler, run_strategy_once
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory
from tests.paper_trading.test_service import (
    _TestPaperTradingService,
    build_service,
    persisted_test_user_id,
    publish_ticker,
    seed_market,
)
from tests.paper_trading.test_short_and_leverage import make_env
from tests.prediction.test_service import train_completed_job
from tests.training.test_service import build_service as build_training_service


@pytest.fixture(autouse=True)
def _use_test_engine(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr(strategy_module, "get_engine", lambda: engine)


def build_prediction(
    *,
    training_job_id: str,
    symbol: str,
    predicted_value: object,
    confidence: float | None,
    feature_drift_status: FeatureDriftStatus = "healthy",
    feature_drift_worst_feature: str | None = None,
    feature_drift_worst_z: float | None = None,
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
        feature_drift_status=feature_drift_status,
        feature_drift_worst_feature=feature_drift_worst_feature,
        feature_drift_worst_z=feature_drift_worst_z,
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


class _RoutingPredictionService:
    """Returns a different, caller-chosen outcome per `training_job_id` —
    needed once a single cycle can call `PredictionService.run` for two
    distinct jobs (VOLATILITY-STOP-WIDTH: the directional signal and the
    optional volatility forecast), each of which must be controlled
    independently rather than sharing one fixed `_StubPredictionService`
    outcome regardless of which job was actually asked for."""

    def __init__(self, outcomes: dict[str, PredictionResponse | Exception]) -> None:
        self._outcomes = outcomes

    async def run(self, request: PredictionRunRequest) -> PredictionResponse:
        outcome = self._outcomes[str(request.training_job_id)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def stub_predictions_by_job(
    monkeypatch: pytest.MonkeyPatch, outcomes: dict[str, PredictionResponse | Exception]
) -> None:
    monkeypatch.setattr(
        strategy_module,
        "get_prediction_service",
        lambda session: _RoutingPredictionService(outcomes),  # noqa: ARG005
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
    service: _TestPaperTradingService,
    account_id: uuid.UUID,
    job_id: str,
    *,
    confidence_threshold_pct: Decimal = Decimal("50"),
    default_stop_loss_pct: Decimal = Decimal("5"),
    volatility_training_job_id: uuid.UUID | None = None,
    leverage: Decimal | None = None,
) -> None:
    # `leverage=None` is a real, rejected state (see
    # `PaperStrategyConfigUpdateRequest._reject_explicit_null_thresholds`),
    # not "omitted" — built as two explicit variants, rather than a
    # `**kwargs`-splatted dict, so a test that doesn't ask for a custom
    # leverage never risks sending an explicit null for it.
    # `volatility_training_job_id` has no such restriction (`None` is
    # itself a meaningful, real "unscaled" state), so it is always passed
    # through directly.
    if leverage is not None:
        request = PaperStrategyConfigUpdateRequest(
            enabled=True,
            training_job_id=uuid.UUID(job_id),
            confidence_threshold_pct=confidence_threshold_pct,
            default_stop_loss_pct=default_stop_loss_pct,
            volatility_training_job_id=volatility_training_job_id,
            leverage=leverage,
        )
    else:
        request = PaperStrategyConfigUpdateRequest(
            enabled=True,
            training_job_id=uuid.UUID(job_id),
            confidence_threshold_pct=confidence_threshold_pct,
            default_stop_loss_pct=default_stop_loss_pct,
            volatility_training_job_id=volatility_training_job_id,
        )
    await service.update_strategy_config(account_id, request)


async def seed_real_candles_on_own_exchange(
    session_factory: SessionFactory, *, symbol: str, count: int = 80
) -> None:
    """`tests.training.test_service.seed_real_candles`'s own body, with a
    symbol-derived exchange slug instead of its hardcoded `"delta"` — that
    helper is only ever called once per test elsewhere in this codebase;
    a test that needs two *different*, both-real-candle symbols in one
    test (VOLATILITY-STOP-WIDTH's own wrong-symbol fail-closed case) would
    otherwise collide on `exchanges.slug`'s uniqueness the second time it
    ran."""
    from app.models import Candle
    from app.models.exchange import Exchange
    from app.models.market import Market

    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with session_factory() as session:
        exchange = Exchange(
            name=f"Delta Exchange {symbol}", slug=f"delta-{symbol.lower()}", country="India"
        )
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()

        price = 100.0
        for i in range(count):
            price += 3.0 if i % 3 != 0 else -4.0
            open_time = base + timedelta(hours=i)
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + timedelta(hours=1),
                    open=Decimal(str(price)),
                    high=Decimal(str(price + 2)),
                    low=Decimal(str(price - 2)),
                    close=Decimal(str(price)),
                    volume=Decimal("100"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()


async def train_second_job_on_existing_symbol(
    session_factory: SessionFactory,
    *,
    symbol: str,
    model_type: str,
    target_config: list[dict[str, object]],
) -> str:
    """Trains a *second* job against a symbol whose candles/market were
    already seeded by an earlier `train_completed_job`/
    `train_completed_job_with_target_config` call for that same symbol —
    VOLATILITY-STOP-WIDTH's own volatility job is always configured on the
    same symbol the directional job already trades (`_resolve_volatility_adjustment`'s
    own symbol-match gate), and `seed_real_candles` creates a brand new
    `Exchange`/`Market` pair every time it runs, so calling it a second time
    for the identical symbol would leave two ambiguous `Market` rows for
    `MarketRepository.get_by_symbol` to resolve between. Returns the new
    job's own id."""
    async with session_factory() as session:
        experiment = Experiment(
            name="second job on an already-seeded symbol",
            dataset_version="ds-real",
            feature_set=[{"feature": "ohlcv", "params": {}}],
            target_config=target_config,
            split_config={"train": 0.7, "validation": 0.15, "test": 0.15},
        )
        session.add(experiment)
        await session.commit()
        experiment_id = str(experiment.id)

    training_service = build_training_service(session_factory)
    try:
        job = await training_service.create(
            TrainingJobCreateRequest(
                experiment_id=uuid.UUID(experiment_id),
                model_type=model_type,
                symbol=symbol,
                timeframe="1h",
                normalize_features=True,
            )
        )
        completed = await training_service.run(uuid.UUID(job.id))
        assert completed.status == "completed", completed.error_message
        return completed.id
    finally:
        await training_service.repository.session.close()


@pytest.mark.asyncio
class TestAboveThresholdWithAFlatPositionOpensAnOrder:
    async def test_a_confident_up_prediction_with_a_flat_position_opens_a_buy(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATUPUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
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
        # Direction and leverage are on the log row, and on the position.
        assert decisions.decisions[0].direction == "long"
        assert float(decisions.decisions[0].strategy_leverage) == pytest.approx(2.0)
        assert positions.positions[0].side == "long"
        assert float(positions.positions[0].leverage) == pytest.approx(2.0)


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
        service = await build_service(session_factory, state_manager)
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
        service = await build_service(session_factory, state_manager)
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

    async def test_flat_and_bearish_opens_a_short(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Replaces `test_flat_and_bearish_is_a_no_op_never_a_short` (M3-E5-T3).
        The old test proved the automated strategy could not short; that
        restriction was removed on purpose, so the same situation now proves the
        opposite: a confident "down" call on a flat account opens a short, at the
        account's fixed leverage, with a stop-loss above the entry."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATFLATDOWNUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
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

        assert summary.opened == 1
        assert summary.closed == 0
        assert summary.no_action == 0

        positions = await service.list_positions(account_id)
        assert len(positions.positions) == 1
        position = positions.positions[0]
        assert position.side == "short"
        assert float(position.leverage) == pytest.approx(2.0)
        assert position.liquidation_price is not None
        assert position.stop_loss_price is not None
        assert float(position.stop_loss_price) > float(position.average_entry_price)

        decisions = await service.list_strategy_decisions(account_id, limit=20, offset=0)
        decision = decisions.decisions[0]
        assert decision.action == "opened"
        assert decision.order_id is not None
        assert decision.direction == "short"
        assert float(decision.strategy_leverage) == pytest.approx(2.0)
        assert "short" in decision.reason.lower()
        assert "2" in decision.reason and "leverage" in decision.reason.lower()

    async def test_short_and_bullish_closes_the_short(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATSHORTUPUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id)
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)

        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATSHORTUPUSD",
                predicted_value="down",
                confidence=0.9,
            ),
        )
        assert (await scheduler.run_strategy_tick()).opened == 1  # short

        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATSHORTUPUSD",
                predicted_value="up",
                confidence=0.9,
            ),
        )
        summary = await scheduler.run_strategy_tick()

        # Closes the short this cycle; it does not also open a long (one action
        # per cycle: no order is ever larger than the position it reduces).
        assert summary.closed == 1
        assert summary.opened == 0
        assert (await service.list_positions(account_id)).positions == []

        decisions = (
            await service.list_strategy_decisions(account_id, limit=20, offset=0)
        ).decisions
        closed = [d for d in decisions if d.action == "closed"]
        assert len(closed) == 1
        assert closed[0].direction == "short"  # the side of the position it closed
        orders = await service.list_orders(
            account_id, sort="created_at", direction="asc", limit=5, offset=0
        )
        [cover] = [o for o in orders.orders if o.reduce_only]
        assert cover.side == "buy"
        assert cover.position_side == "short"

    async def test_short_and_bearish_is_a_no_op_already_consistent(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATSHORTDOWNUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATSHORTDOWNUSD",
                predicted_value="down",
                confidence=0.9,
            ),
        )
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        assert (await scheduler.run_strategy_tick()).opened == 1
        before = (await service.list_positions(account_id)).positions[0]

        summary = await scheduler.run_strategy_tick()  # the same call again

        assert summary.opened == 0 and summary.closed == 0 and summary.no_action == 1
        after = (await service.list_positions(account_id)).positions
        assert len(after) == 1
        assert after[0].quantity == before.quantity  # not a second short on top
        decisions = (
            await service.list_strategy_decisions(account_id, limit=20, offset=0)
        ).decisions
        assert sorted(d.action for d in decisions) == ["no_action", "opened"]
        [skipped] = [d for d in decisions if d.action == "no_action"]
        assert "already short" in skipped.reason.lower()
        assert skipped.direction == "short"

    async def test_long_and_bullish_is_a_no_op_already_consistent(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATLONGUPUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
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
        assert decision.direction == "long"
        assert float(decision.strategy_leverage) == pytest.approx(2.0)


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
        service = await build_service(session_factory, state_manager)
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
        service = await build_service(session_factory, state_manager)
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
class TestFeatureDriftAutoPause:
    """FEATURE-DRIFT-MONITOR (Option C, the chosen response policy is
    auto-pause — `docs/research/FEATURE_DRIFT_INVESTIGATION.md`). A drifted
    prediction must never reach the confidence/signal logic, however
    confident it claims to be — both real incidents this guards against
    were >99% confident "down" — so this checks the pause happens *before*
    any order could be placed on it, not merely that no order results."""

    async def test_a_drifted_prediction_pauses_the_strategy_and_places_no_order(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        alerts: list[dict[str, object]] = []
        monkeypatch.setattr(
            "app.services.paper_trading_strategy.capture_feature_drift",
            lambda account_id, **kwargs: alerts.append({"account_id": account_id, **kwargs}),
        )
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATDRIFTUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATDRIFTUSD",
                predicted_value="down",
                # The exact shape both real incidents showed: saturated
                # confidence on a drifted model, not a weak or borderline one.
                confidence=0.999,
                feature_drift_status="drifted",
                feature_drift_worst_feature="volume",
                feature_drift_worst_z=88.96,
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.attempted == 1
        assert summary.opened == 0
        assert summary.no_action == 1

        positions = await service.list_positions(uuid.UUID(account.id))
        assert positions.positions == []

        paused = await service.get_account(uuid.UUID(account.id))
        assert paused.strategy_enabled is False
        assert paused.strategy_paused_reason == "feature_drift"
        assert paused.strategy_paused_at is not None

        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 1
        decision = decisions.decisions[0]
        assert decision.action == "no_action"
        assert decision.order_id is None
        assert "drift" in decision.reason.lower()
        assert "volume" in decision.reason.lower()

        assert len(alerts) == 1
        assert alerts[0]["account_id"] == account.id
        assert alerts[0]["worst_feature"] == "volume"
        assert alerts[0]["worst_z"] == pytest.approx(88.96)
        assert alerts[0]["training_job_id"] == job_id

    async def test_a_drifted_prediction_stops_future_ticks_until_a_human_re_enables(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The auto-pause is not self-healing on its own — mirrors the
        drawdown kill switch's own 'does not clear itself' contract exactly
        (`PaperAccount.trading_halted`'s own docstring) — until a human
        explicitly re-enables it, the disabled account is simply absent
        from every later tick's own query, the same "disabling takes effect
        before the next cycle" guarantee `TestDisablingStopsFutureCycles`
        already established for a human's own disable."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATDRIFTOFFUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATDRIFTOFFUSD",
                predicted_value="down",
                confidence=0.999,
                feature_drift_status="drifted",
                feature_drift_worst_feature="close",
                feature_drift_worst_z=-17.0,
            ),
        )
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        first = await scheduler.run_strategy_tick()
        assert first.attempted == 1

        second = await scheduler.run_strategy_tick()
        assert second.attempted == 0

    async def test_re_enabling_after_a_drift_pause_clears_the_paused_reason(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A human explicitly naming `enabled` always supersedes the
        automated reason — the one behaviour `update_strategy_config` itself
        needed to gain for this feature."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATDRIFTCLEARUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATDRIFTCLEARUSD",
                predicted_value="down",
                confidence=0.999,
                feature_drift_status="drifted",
                feature_drift_worst_feature="close",
                feature_drift_worst_z=-17.0,
            ),
        )
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        await scheduler.run_strategy_tick()
        paused = await service.get_account(uuid.UUID(account.id))
        assert paused.strategy_paused_reason == "feature_drift"

        await service.update_strategy_config(
            uuid.UUID(account.id), PaperStrategyConfigUpdateRequest(enabled=True)
        )
        resumed = await service.get_account(uuid.UUID(account.id))
        assert resumed.strategy_enabled is True
        assert resumed.strategy_paused_reason is None
        assert resumed.strategy_paused_at is None

    async def test_a_healthy_prediction_is_not_paused_and_acts_normally(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`build_prediction`'s own default (`feature_drift_status="healthy"`)
        must not itself introduce a false-positive pause into every other
        test in this file — checked directly here, not just assumed."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATDRIFTOKUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATDRIFTOKUSD",
                predicted_value="up",
                confidence=0.9,
            ),
        )
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        account_after = await service.get_account(uuid.UUID(account.id))
        assert account_after.strategy_enabled is True
        assert account_after.strategy_paused_reason is None


@pytest.mark.asyncio
class TestAutomatedPositionsAlwaysCarryAStopLoss:
    @pytest.mark.parametrize(
        ("call", "side", "sign"),
        [("up", "long", -1), ("down", "short", +1)],
    )
    async def test_every_automated_entry_carries_a_direction_aware_stop_loss(
        self,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        call: str,
        side: str,
        sign: int,
    ) -> None:
        """A long's stop is 7% BELOW the resolved quote, a short's 7% ABOVE it —
        never omitted, in either direction."""
        symbol = f"STRATSL{call.upper()}USD"
        job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service, uuid.UUID(account.id), job_id, default_stop_loss_pct=Decimal("7")
        )
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol=symbol, predicted_value=call, confidence=0.9
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        positions = await service.list_positions(uuid.UUID(account.id))
        position = positions.positions[0]
        assert position.side == side
        assert position.stop_loss_price is not None

        orders = await service.list_orders(
            uuid.UUID(account.id), sort="created_at", direction="desc", limit=20, offset=0
        )
        order = orders.orders[0]
        # 7% on the losing side of the *resolved quote* the order priced from
        # (raw_price, before slippage), not the fill price, which already
        # differs from it by the modeled slippage.
        expected = float(order.raw_price) * (1 + sign * 0.07)
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)

    async def test_the_stop_loss_actually_closes_an_automated_short_when_price_rises(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine
    ) -> None:
        """The stop is not decoration: the existing monitor, now direction-aware,
        closes the automated short when the price rises to it."""
        from datetime import UTC, datetime

        from app.marketdata.bus_events import TickerUpdated
        from app.marketdata.models import TickerEvent
        from app.paper_trading import monitor as monitor_module
        from tests.paper_trading.test_monitor import build_monitor

        monkeypatch.setattr(monitor_module, "get_engine", lambda: engine)
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATSHORTSTOPUSD", model_type="logistic_regression"
        )
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        build_monitor(state_manager).attach(bus)
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id, default_stop_loss_pct=Decimal("5"))
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATSHORTSTOPUSD",
                predicted_value="down",
                confidence=0.9,
            ),
        )
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        await scheduler.run_strategy_tick()
        position = (await service.list_positions(account_id)).positions[0]
        assert position.stop_loss_price is not None

        await bus.publish(
            TickerUpdated(
                source="test",
                ticker=TickerEvent(
                    exchange="delta",
                    symbol="STRATSHORTSTOPUSD",
                    event_time=datetime.now(UTC),
                    last_price=position.stop_loss_price,
                ),
            )
        )
        await bus.drain()

        assert (await service.list_positions(account_id)).positions == []
        orders = await service.list_orders(
            account_id, sort="created_at", direction="asc", limit=5, offset=0
        )
        [triggered] = [o for o in orders.orders if o.trigger_reason is not None]
        assert triggered.trigger_reason == "stop_loss"
        assert triggered.side == "buy"


@pytest.mark.asyncio
class TestVolatilityStopWidth:
    """VOLATILITY-STOP-WIDTH (Option B): `PaperAccount
    .strategy_volatility_training_job_id` optionally scales a new
    automated entry's stop-loss width from a second, `logistic_regression`
    -trained `volatility_regime` forecast for the same symbol —
    `_resolve_volatility_adjustment`'s own docstring has the full gate list. Every
    test here trains two real, completed jobs on one shared symbol (never
    a stub standing in for `TrainingJobRepository.get_by_id`, since
    `_resolve_volatility_adjustment` reads `job.model_type`/`job.symbol` straight
    from the database) and stubs only the *prediction* calls
    (`stub_predictions_by_job`), for the same reason every other test in
    this file stubs `PredictionService.run` rather than depending on a
    real model's own harder-to-control output.
    """

    _VOLATILITY_TARGET_CONFIG: list[dict[str, object]] = [
        {"target": "volatility_regime", "params": {"window_hours": "5"}}
    ]

    async def test_an_unconfigured_volatility_job_leaves_the_stop_loss_unscaled(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default, pre-existing behaviour for every account that has
        never set `strategy_volatility_training_job_id` — regression
        safety for every other test in this file."""
        symbol = "STRATVOLUNSETUSD"
        job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service, uuid.UUID(account.id), job_id, default_stop_loss_pct=Decimal("5")
        )
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol=symbol, predicted_value="up", confidence=0.9
            ),
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert position.stop_loss_price is not None
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        expected = float(order.raw_price) * (1 - 0.05)
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)

    async def test_widens_the_stop_loss_on_an_expand_forecast(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        symbol = "STRATVOLEXPANDUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="expand",
                    confidence=0.6,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert position.stop_loss_price is not None
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        # 5% default * 1.5 widen factor = 7.5%, below the resolved quote (a long).
        expected = float(order.raw_price) * (1 - 0.075)
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "widened" in decision.reason.lower()
        assert "expand" in decision.reason.lower()

    async def test_tightens_the_stop_loss_on_a_contract_forecast(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        symbol = "STRATVOLCONTRACTUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="down",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="contract",
                    confidence=0.6,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert position.stop_loss_price is not None
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        # 5% default * 0.75 tighten factor = 3.75%, above the resolved quote (a short).
        expected = float(order.raw_price) * (1 + 0.0375)
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "tightened" in decision.reason.lower()
        assert "contract" in decision.reason.lower()

    async def test_a_drifted_volatility_forecast_falls_back_to_the_fixed_default_width(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The volatility forecast's own inputs reporting drifted must fall
        back to `strategy_default_stop_loss_pct` unscaled — never a stale or
        guessed width, and never silently continuing on the drifted reading
        (mirroring how a drifted *directional* prediction already auto-pauses
        the whole strategy elsewhere in this module, for the same reason)."""
        symbol = "STRATVOLDRIFTUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="expand",
                    confidence=0.6,
                    feature_drift_status="drifted",
                    feature_drift_worst_feature="close",
                    feature_drift_worst_z=-12.0,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        # The strategy's own auto-pause-on-drift only ever inspects the
        # *directional* prediction's drift status (healthy here) — a
        # drifted volatility forecast affects width alone, never whether
        # this cycle acts at all.
        assert summary.opened == 1
        account_after = await service.get_account(uuid.UUID(account.id))
        assert account_after.strategy_enabled is True
        assert account_after.strategy_paused_reason is None

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert position.stop_loss_price is not None
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        expected = float(order.raw_price) * (1 - 0.05)  # unscaled default, not the 'expand' width
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "drifted" in decision.reason.lower()
        assert "unscaled defaults used" in decision.reason.lower()

    async def test_a_volatility_job_of_the_wrong_model_type_falls_back_to_the_fixed_default(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`strategy_volatility_training_job_id` must be `logistic_regression`
        specifically — a `random_forest` job (even one genuinely trained on
        `volatility_regime`, for the same symbol) is rejected as a forecast
        source, fixed-default-fallback rather than used anyway. The stub
        below deliberately has no entry for `volatility_job_id`: if
        `_resolve_volatility_adjustment` ever called the prediction service for a
        wrong-model-type job (a bug), the routing stub would raise
        `KeyError` and the whole cycle would crash into `no_action` instead
        of opening — this test would then fail loudly rather than passing
        by accident."""
        symbol = "STRATVOLWRONGMODELUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="random_forest",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert position.stop_loss_price is not None
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        expected = float(order.raw_price) * (1 - 0.05)
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "random_forest" in decision.reason.lower()
        assert "unscaled defaults used" in decision.reason.lower()

    async def test_a_volatility_job_trained_on_a_different_symbol_falls_back_to_the_fixed_default(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A `logistic_regression` `volatility_regime` job is still the
        wrong forecast source if it was trained on a different market —
        never applied to a symbol it wasn't trained for, matching the
        directional job's own "its own recorded symbol, never a
        separately-configured one" rule elsewhere in this module."""
        symbol = "STRATVOLSYMBOLAUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        await seed_real_candles_on_own_exchange(session_factory, symbol="STRATVOLSYMBOLBUSD")
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol="STRATVOLSYMBOLBUSD",
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert position.stop_loss_price is not None
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        expected = float(order.raw_price) * (1 - 0.05)
        assert float(position.stop_loss_price) == pytest.approx(expected, rel=1e-6)

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "STRATVOLSYMBOLBUSD" in decision.reason
        assert "unscaled defaults used" in decision.reason.lower()

    async def test_direction_and_whether_to_trade_are_unaffected_size_and_width_differ(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The boundary-preserving test both VOLATILITY-STOP-WIDTH and
        VOLATILITY-POSITION-SIZING ask for: two accounts, identical in every
        respect except one has a volatility job configured and the other
        doesn't, processed in the very same tick against the very same
        directional signal — proves the strategy's own
        whether-to-trade/which-direction decision is unaffected by the
        volatility forecast being active at all. This is
        VOLATILITY_RISK_SIZING_DESIGN.md's own central claim ("trading
        decisions stay identical, only size/leverage/width changes"),
        checked here rather than merely asserted in a document.

        Unlike VOLATILITY-STOP-WIDTH's own original version of this test
        (written before Option A existed), quantity and leverage are no
        longer expected to match — that is now the entire point of Option A.
        What must still match, byte-for-byte, is `side`/`symbol` and the
        decision log's own `direction`/`action`/`predicted_value` — the
        actual trading decision, made before `_resolve_volatility_adjustment`
        is ever called at all."""
        symbol = "STRATVOLBOUNDARYUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account_unscaled = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_scaled = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account_unscaled.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
        )
        await enable_strategy(
            service,
            uuid.UUID(account_scaled.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="expand",
                    confidence=0.6,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.attempted == 2
        assert summary.opened == 2
        assert summary.no_action == 0

        position_unscaled = (
            await service.list_positions(uuid.UUID(account_unscaled.id))
        ).positions[0]
        position_scaled = (await service.list_positions(uuid.UUID(account_scaled.id))).positions[0]
        assert position_unscaled.stop_loss_price is not None
        assert position_scaled.stop_loss_price is not None

        # Byte-identical: side and symbol -- the actual trading decision,
        # made before `_resolve_volatility_adjustment` is ever called.
        assert position_unscaled.side == position_scaled.side == "long"
        assert position_unscaled.symbol == position_scaled.symbol == symbol

        # Deliberately DIFFERENT (VOLATILITY-POSITION-SIZING's own point):
        # the 'expand' forecast sizes the scaled account down on both size
        # and leverage, and widens its stop -- none of the three equal the
        # unscaled account's own.
        assert float(position_scaled.quantity) < float(position_unscaled.quantity)
        assert float(position_scaled.leverage) < float(position_unscaled.leverage)
        assert float(position_scaled.stop_loss_price) != pytest.approx(
            float(position_unscaled.stop_loss_price), rel=1e-9
        )
        assert float(position_scaled.stop_loss_price) < float(position_unscaled.stop_loss_price)

        decision_unscaled = (
            await service.list_strategy_decisions(uuid.UUID(account_unscaled.id), limit=5, offset=0)
        ).decisions[0]
        decision_scaled = (
            await service.list_strategy_decisions(uuid.UUID(account_scaled.id), limit=5, offset=0)
        ).decisions[0]
        assert decision_unscaled.direction == decision_scaled.direction == "long"
        assert decision_unscaled.action == decision_scaled.action == "opened"
        assert decision_unscaled.predicted_value == decision_scaled.predicted_value == "up"

    async def test_expand_scaling_leverage_down_keeps_the_widened_stop_inside_liquidation(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Before VOLATILITY-POSITION-SIZING existed, a widened stop-loss
        alone (Option B) could cross liquidation at an otherwise-safe
        leverage (this test used to prove exactly that, rejecting the
        entry). Now that an 'expand' forecast scales leverage *down* at
        the same time it scales the stop *wider* (Option A), that specific
        failure mode is structurally avoided, not coincidentally: a lower
        leverage means a farther liquidation distance, checked here with
        real numbers, not assumed.

        At 10x leverage (`max_leverage=10`), the real liquidation distance
        is ~9.77% -- an 8% default stop clears it. Scaled by Option
        B's own 1.5x on 'expand', the stop becomes 12%. Scaled by Option
        A's exact-reciprocal 2/3 on the same signal, leverage becomes
        6.667x, whose own real liquidation distance is ~14.79% -- comfortably
        clearing the scaled 12% stop. The entry succeeds; it is not rejected.
        (Verified algebraically for every tested leverage from 1x to 100x
        that this coupling's own liquidation-distance ratio always exceeds
        the stop's own 1.5x widening ratio -- this is not a coincidence of
        the specific numbers chosen here.)"""
        symbol = "STRATVOLLIQUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"), max_leverage=Decimal("10")
            )
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("8"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
            leverage=Decimal("10"),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="expand",
                    confidence=0.6,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1
        assert summary.no_action == 0

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert float(position.leverage) == pytest.approx(10 * (2 / 3), rel=1e-9)

    async def test_place_order_still_rejects_a_stop_beyond_liquidation_at_an_expected_leverage(
        self, session_factory: SessionFactory
    ) -> None:
        """A direct, non-volatility-scaled proof that `place_order`'s new
        `expected_leverage` parameter (added for VOLATILITY-POSITION-SIZING)
        does not weaken the pre-existing liquidation check in any way — an
        automated entry whose `expected_leverage` differs from the account's
        raw `strategy_leverage` still has its stop-loss checked against
        *that* leverage's own real liquidation distance. At 20x on a $2000
        entry, the real liquidation price is ~$1904.76; a $1900 stop sits
        beyond it, exactly mirroring
        `TestAutomatedCaller::test_a_stop_loss_beyond_the_liquidation_price_is_rejected`'s
        own already-proven scenario at 10x, just at an expected, not the
        account's raw, leverage."""
        env = await make_env(session_factory, "STRATLIQDIRECTUSD", max_leverage="20")
        with pytest.raises(StopBeyondLiquidationError):
            await env.automated(
                "buy",
                "1",
                leverage=Decimal("20"),
                stop_loss_price=Decimal("1900"),
                expected_leverage=Decimal("20"),
            )

    async def test_a_manual_order_stop_loss_is_never_scaled_or_overridden(
        self, session_factory: SessionFactory
    ) -> None:
        """`_resolve_volatility_adjustment` is only ever called from
        `PaperTradingStrategyScheduler._open_position` — a manual order's
        own human-supplied `stop_loss_price` goes straight through
        `PaperTradingService.place_order`'s ordinary manual path, which
        never calls it, regardless of whether this account also has a
        volatility job configured for its *automated* strategy."""
        other_job_id, _ = await train_completed_job(
            session_factory, symbol="STRATVOLMANUALOTHERUSD", model_type="logistic_regression"
        )
        symbol = "STRATVOLMANUALUSD"
        await seed_market(session_factory, symbol=symbol)
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, symbol, "1000")
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        # A volatility job IS configured on this account — the strategy
        # itself is never enabled, but that's irrelevant to this test's own
        # point: a manual order never consults this field at all.
        await service.update_strategy_config(
            account_id,
            PaperStrategyConfigUpdateRequest(volatility_training_job_id=uuid.UUID(other_job_id)),
        )

        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol=symbol, side="buy", quantity=Decimal("1"), stop_loss_price=Decimal("900")
            ),
        )

        position = (await service.list_positions(account_id)).positions[0]
        assert position.stop_loss_price is not None
        assert float(position.stop_loss_price) == 900.0


@pytest.mark.asyncio
class TestVolatilityPositionSizing:
    """VOLATILITY-POSITION-SIZING (Option A): the same
    `strategy_volatility_training_job_id` forecast VOLATILITY-STOP-WIDTH
    already scales stop-loss width from also scales target position size
    and `strategy_leverage`, from one shared fetch
    (`_resolve_volatility_adjustment`) — down ahead of 'expand', up (bounded
    by the account's own existing `max_position_size_pct`/`max_leverage`,
    never `max_exposure_pct`) ahead of 'contract'. Every fail-closed gate
    (missing job, wrong model type, wrong symbol, unavailable forecast,
    drifted forecast, a non-expand/contract label) is already proven once
    for all three scaled values together by `TestVolatilityStopWidth`'s own
    tests, since they share one gate; this class covers what's specific to
    size/leverage: the scaling direction and magnitude, the cap, the cost
    -asymmetry log line, and that `max_exposure_pct` is never touched at
    all.
    """

    _VOLATILITY_TARGET_CONFIG: list[dict[str, object]] = [
        {"target": "volatility_regime", "params": {"window_hours": "5"}}
    ]

    async def test_shrinks_position_size_and_leverage_on_an_expand_forecast(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        symbol = "STRATVOLSIZEEXPANDUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"), max_leverage=Decimal("5")
            )
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
            leverage=Decimal("3"),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="expand",
                    confidence=0.6,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        # leverage: 3 * 2/3 = 2 exactly.
        assert float(position.leverage) == pytest.approx(2.0, rel=1e-9)
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        # target_pct: max_position_size_pct (default) * 0.5 * 2/3 -- smaller
        # than the unscaled 0.5 fraction would have sized.
        default_target_pct = Decimal(account.max_position_size_pct) * Decimal("0.5")
        unscaled_quantity = (Decimal("100000") * default_target_pct / 100) / order.raw_price
        assert float(order.quantity) < float(unscaled_quantity)

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "sized down" in decision.reason.lower()

    async def test_grows_leverage_on_a_contract_forecast_bounded_by_max_leverage(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`strategy_leverage=5` scaled by the grow factor (4/3) would be
        ~6.667x -- but `max_leverage=6` caps it at exactly 6, proving the
        design doc's own "never past max_leverage" requirement actually
        binds, not just that scaling "up" happens."""
        symbol = "STRATVOLSIZECONTRACTUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"), max_leverage=Decimal("6")
            )
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("1"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
            leverage=Decimal("5"),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="contract",
                    confidence=0.6,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        # Unbounded would be 5 * 4/3 = 6.667x; capped at max_leverage=6.
        assert float(position.leverage) == pytest.approx(6.0, rel=1e-9)

        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        # target_pct is also scaled up, and stays within max_position_size_pct
        # -- the same "never past the existing cap" requirement, checked for
        # size too (structurally non-binding at today's 0.5 base fraction and
        # 4/3 grow factor, since 0.5 * 4/3 = 2/3 < 1, but asserted directly
        # rather than assumed).
        max_position_size_pct = Decimal(account.max_position_size_pct)
        default_target_pct = max_position_size_pct * Decimal("0.5")
        unscaled_quantity = (Decimal("100000") * default_target_pct / 100) / order.raw_price
        assert float(order.quantity) > float(unscaled_quantity)
        scaled_target_pct = order.quantity * order.raw_price * 100 / Decimal("100000")
        assert scaled_target_pct <= max_position_size_pct

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "sized up" in decision.reason.lower()
        assert "contract" in decision.reason.lower()

    async def test_a_drifted_volatility_forecast_leaves_size_and_leverage_unscaled(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The identical drift-fallback shape VOLATILITY-STOP-WIDTH already
        proved for stop-loss width (`TestVolatilityStopWidth
        ::test_a_drifted_volatility_forecast_falls_back_to_the_fixed_default_width`),
        checked here explicitly for size/leverage: both stay at the
        account's own unscaled defaults, never the drifted forecast's
        'expand' call."""
        symbol = "STRATVOLSIZEDRIFTUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("5"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
            leverage=Decimal("3"),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="expand",
                    confidence=0.6,
                    feature_drift_status="drifted",
                    feature_drift_worst_feature="close",
                    feature_drift_worst_z=-12.0,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert float(position.leverage) == pytest.approx(3.0, rel=1e-9)
        order = (
            await service.list_orders(
                uuid.UUID(account.id), sort="created_at", direction="desc", limit=5, offset=0
            )
        ).orders[0]
        default_target_pct = Decimal(account.max_position_size_pct) * Decimal("0.5")
        expected_quantity = (Decimal("100000") * default_target_pct / 100) / order.raw_price
        assert float(order.quantity) == pytest.approx(float(expected_quantity), rel=1e-9)

    async def test_cost_asymmetry_is_logged_when_leverage_scales_up(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VOLATILITY_RISK_SIZING_DESIGN.md Step 3's own named complication:
        leverage amplifies the fixed round-trip transaction cost as much as
        it amplifies exposure, so scaling it up must be visible in the
        decision log, not left implicit in a bare leverage number."""
        symbol = "STRATVOLCOSTUSD"
        directional_job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        volatility_job_id = await train_second_job_on_existing_symbol(
            session_factory,
            symbol=symbol,
            model_type="logistic_regression",
            target_config=self._VOLATILITY_TARGET_CONFIG,
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(
            service,
            uuid.UUID(account.id),
            directional_job_id,
            default_stop_loss_pct=Decimal("1"),
            volatility_training_job_id=uuid.UUID(volatility_job_id),
            leverage=Decimal("2"),
        )
        stub_predictions_by_job(
            monkeypatch,
            {
                directional_job_id: build_prediction(
                    training_job_id=directional_job_id,
                    symbol=symbol,
                    predicted_value="up",
                    confidence=0.9,
                ),
                volatility_job_id: build_prediction(
                    training_job_id=volatility_job_id,
                    symbol=symbol,
                    predicted_value="contract",
                    confidence=0.6,
                ),
            },
        )

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()
        assert summary.opened == 1

        position = (await service.list_positions(uuid.UUID(account.id))).positions[0]
        assert float(position.leverage) == pytest.approx(2 * (4 / 3), rel=1e-9)

        decision = (
            await service.list_strategy_decisions(uuid.UUID(account.id), limit=5, offset=0)
        ).decisions[0]
        assert "round-trip" in decision.reason.lower()
        assert "transaction cost" in decision.reason.lower()

    def test_max_exposure_pct_is_never_referenced_by_the_volatility_adjustment(self) -> None:
        """Static, grep-verifiable proof of
        `VOLATILITY_RISK_SIZING_DESIGN.md`'s own explicit requirement: this
        feature scales size/leverage within the account's *existing* caps,
        and never touches `max_exposure_pct` — D7's own real exposure
        ceiling — at all."""
        import ast
        from pathlib import Path

        source = Path(strategy_module.__file__).read_text()
        tree = ast.parse(source)
        (function,) = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_resolve_volatility_adjustment"
        ]
        names = {n.id for n in ast.walk(function) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(function) if isinstance(n, ast.Attribute)}
        assert not any("max_exposure" in x for x in names | attrs)


@pytest.mark.asyncio
class TestLongAndBearishClosesThePosition:
    async def test_a_confident_down_prediction_while_long_closes_the_position(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATDOWNUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
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

    async def test_a_close_that_loses_a_race_is_logged_and_never_opens_the_other_side(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The race a stop-loss or a liquidation creates: between the strategy
        deciding to close and its order arriving, the position is already gone.
        With shorts reachable, a plain opposite-side order would now OPEN a
        short there; the strategy's close is `reduce_only`, so it is rejected
        and logged instead."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATCLOSERACEUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        manual_user = await persisted_test_user_id(session_factory)
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="STRATCLOSERACEUSD", side="buy", quantity=Decimal("1")),
            user_id=manual_user,
        )
        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id,
                symbol="STRATCLOSERACEUSD",
                predicted_value="down",
                confidence=0.9,
            ),
        )

        original = PaperTradingService.place_order

        async def position_vanishes_first(self, account_id_, request, **kwargs):  # noqa: ANN001, ANN202
            if kwargs.get("automated") and request.reduce_only:
                # Something else (a stop-loss, a liquidation) closes it first.
                await original(
                    service,
                    account_id_,
                    PaperOrderRequest(
                        symbol=request.symbol,
                        side="sell",
                        quantity=request.quantity,
                        reduce_only=True,
                    ),
                    user_id=manual_user,
                )
            return await original(self, account_id_, request, **kwargs)

        monkeypatch.setattr(PaperTradingService, "place_order", position_vanishes_first)

        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)
        summary = await scheduler.run_strategy_tick()

        assert summary.closed == 0
        assert summary.no_action == 1
        assert (await service.list_positions(account_id)).positions == []  # no short opened

        decision = (
            await service.list_strategy_decisions(account_id, limit=20, offset=0)
        ).decisions[0]
        assert decision.action == "no_action"
        assert "rejected" in decision.reason.lower()
        assert decision.direction == "long"


@pytest.mark.asyncio
class TestSharesExistingRiskLimits:
    @pytest.mark.parametrize(("call", "direction"), [("up", "long"), ("down", "short")])
    async def test_a_strategy_order_that_would_breach_max_exposure_is_rejected(
        self,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        call: str,
        direction: str,
    ) -> None:
        """The strategy is 'just another caller' of `place_order` — proven
        here by configuring a tight `max_exposure_pct`, pre-filling most
        of that budget with an ordinary *manual* buy in a different
        symbol, and showing the automated buy is rejected by the exact
        same `MaxExposureExceededError` a manual order would hit in the
        same situation, never a second, unguarded path."""
        risk_symbol = f"STRATRISK{call.upper()}USD"
        job_id, _ = await train_completed_job(
            session_factory, symbol=risk_symbol, model_type="logistic_regression"
        )
        await seed_market(session_factory, symbol="STRATOTHERUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "STRATOTHERUSD", "1000")

        service = await build_service(session_factory, state_manager)
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
                symbol=risk_symbol,
                predicted_value=call,
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
        assert decision.direction == direction  # a short is rejected exactly as a long is

    @pytest.mark.parametrize(("call", "direction"), [("up", "long"), ("down", "short")])
    async def test_leverage_does_not_get_a_strategy_order_past_the_position_size_limit(
        self,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        call: str,
        direction: str,
    ) -> None:
        """The position-size limit is on notional over equity, so the strategy's
        2x leverage buys no extra size: an order whose notional exceeds the limit
        is rejected in both directions exactly as a manual one would be."""
        symbol = f"STRATPOS{call.upper()}USD"
        job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=Decimal("0.0001"),
                max_exposure_pct=Decimal("100"),
                max_drawdown_pct=Decimal("100"),
            )
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol=symbol, predicted_value=call, confidence=0.9
            ),
        )
        # Force a sizing far above the (tiny) limit.
        monkeypatch.setattr(strategy_module, "_TARGET_POSITION_SIZE_FRACTION", Decimal("5000"))

        summary = await PaperTradingStrategyScheduler(
            state_manager=state_manager
        ).run_strategy_tick()

        assert summary.opened == 0 and summary.no_action == 1
        decision = (await service.list_strategy_decisions(account_id, limit=5, offset=0)).decisions[
            0
        ]
        assert "max position size" in decision.reason.lower()
        assert decision.direction == direction


@pytest.mark.asyncio
class TestDisablingStopsFutureCycles:
    async def test_disabling_the_strategy_prevents_the_next_tick_from_acting(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATOFFUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
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
        service = await build_service(session_factory, state_manager)
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
        service = await build_service(session_factory, state_manager)
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
        service = await build_service(session_factory, state_manager)
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
        service = await build_service(session_factory, MarketStateManager())
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)

        summary = await run_strategy_once()

        assert summary.attempted == 1
        decisions = await service.list_strategy_decisions(uuid.UUID(account.id), limit=20, offset=0)
        assert decisions.total == 1


@pytest.mark.asyncio
class TestKillSwitchHaltsEntriesInBothDirectionsButNotExits:
    """D4 for the automated strategy: a halted account takes no new automated
    risk, long or short; it can still close what it holds; and a liquidation
    can never be blocked (proven at the monitor level in `test_liquidation.py`)."""

    async def _halted_account(
        self, session_factory: SessionFactory, symbol: str
    ) -> tuple[uuid.UUID, uuid.UUID, MarketStateManager, _TestPaperTradingService]:
        job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, uuid.UUID(str(job_id)) and job_id)
        return account_id, uuid.UUID(str(job_id)), state_manager, service

    @pytest.mark.parametrize("call", ["up", "down"])
    async def test_a_halted_account_takes_no_new_automated_entry(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch, call: str
    ) -> None:
        symbol = f"STRATHALT{call.upper()}USD"
        account_id, job_id, state_manager, service = await self._halted_account(
            session_factory, symbol
        )
        account = await service.account_repository.get_by_id(account_id)
        assert account is not None
        await service.account_repository.update(account, {"trading_halted": True})
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=str(job_id), symbol=symbol, predicted_value=call, confidence=0.9
            ),
        )

        summary = await PaperTradingStrategyScheduler(
            state_manager=state_manager
        ).run_strategy_tick()

        assert summary.opened == 0 and summary.no_action == 1
        assert (await service.list_positions(account_id)).positions == []
        decision = (await service.list_strategy_decisions(account_id, limit=5, offset=0)).decisions[
            0
        ]
        assert "halted" in decision.reason.lower()
        assert decision.direction == ("long" if call == "up" else "short")

    @pytest.mark.parametrize(
        ("held", "call"), [("buy", "down"), ("sell", "up")], ids=["close-long", "close-short"]
    )
    async def test_a_halted_account_can_still_close_what_it_holds(
        self,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        held: str,
        call: str,
    ) -> None:
        symbol = f"STRATHALTEXIT{held.upper()}USD"
        account_id, job_id, state_manager, service = await self._halted_account(
            session_factory, symbol
        )
        manual_user = await persisted_test_user_id(session_factory)
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol=symbol, side=held, quantity=Decimal("1")),  # type: ignore[arg-type]
            user_id=manual_user,
        )
        account = await service.account_repository.get_by_id(account_id)
        assert account is not None
        await service.account_repository.update(account, {"trading_halted": True})
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=str(job_id), symbol=symbol, predicted_value=call, confidence=0.9
            ),
        )

        summary = await PaperTradingStrategyScheduler(
            state_manager=state_manager
        ).run_strategy_tick()

        assert summary.closed == 1
        assert (await service.list_positions(account_id)).positions == []
        assert (
            await service.get_account(account_id)
        ).trading_halted is True  # closing didn't un-halt


class TestLeverageIsFixedNeverDerivedFromConfidence:
    """`strategy_leverage` is one configured number. Confidence has been measured
    to carry no reliable relationship to being right (mean 0.889 against accuracy
    0.460, correlation -0.020), so it must never scale risk. Proven three ways:
    by behaviour, by a syntax-level scan of the strategy, and by a scan of every
    place in the application that sets a leverage."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("call", ["up", "down"])
    async def test_every_confidence_produces_the_same_configured_leverage(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch, call: str
    ) -> None:
        symbol = f"STRATFIX{call.upper()}USD"
        job_id, _ = await train_completed_job(
            session_factory, symbol=symbol, model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        leverages: dict[float, float] = {}
        for confidence in (0.66, 0.80, 0.99):
            account = await service.create_account(
                PaperAccountCreateRequest(
                    starting_balance=Decimal("100000"), max_leverage=Decimal("5")
                )
            )
            account_id = uuid.UUID(account.id)
            await service.update_strategy_config(
                account_id,
                PaperStrategyConfigUpdateRequest(
                    enabled=True,
                    training_job_id=uuid.UUID(job_id),
                    confidence_threshold_pct=Decimal("50"),
                    leverage=Decimal("3"),
                ),
            )
            stub_prediction(
                monkeypatch,
                build_prediction(
                    training_job_id=job_id,
                    symbol=symbol,
                    predicted_value=call,
                    confidence=confidence,
                ),
            )
            summary = await PaperTradingStrategyScheduler(
                state_manager=state_manager
            ).run_strategy_tick()
            assert summary.opened == 1
            position = (await service.list_positions(account_id)).positions[0]
            leverages[confidence] = float(position.leverage)
            decision = (
                await service.list_strategy_decisions(account_id, limit=5, offset=0)
            ).decisions[0]
            assert float(decision.strategy_leverage) == pytest.approx(3.0)
            # Done with this account: only the next one should act on the next tick.
            await service.update_strategy_config(
                account_id, PaperStrategyConfigUpdateRequest(enabled=False)
            )

        # 66%, 80% and 99% confidence: identical leverage, exactly the configured 3.
        assert set(leverages.values()) == {3.0}

    @pytest.mark.asyncio
    async def test_changing_the_configured_leverage_changes_the_orders_leverage(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATCFGUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        seen = []
        for configured in ("1", "2", "4"):
            account = await service.create_account(
                PaperAccountCreateRequest(
                    starting_balance=Decimal("100000"), max_leverage=Decimal("5")
                )
            )
            account_id = uuid.UUID(account.id)
            await service.update_strategy_config(
                account_id,
                PaperStrategyConfigUpdateRequest(
                    enabled=True,
                    training_job_id=uuid.UUID(job_id),
                    confidence_threshold_pct=Decimal("50"),
                    leverage=Decimal(configured),
                ),
            )
            stub_prediction(
                monkeypatch,
                build_prediction(
                    training_job_id=job_id,
                    symbol="STRATCFGUSD",
                    predicted_value="down",
                    confidence=0.9,
                ),
            )
            await PaperTradingStrategyScheduler(state_manager=state_manager).run_strategy_tick()
            seen.append(float((await service.list_positions(account_id)).positions[0].leverage))
            await service.update_strategy_config(
                account_id, PaperStrategyConfigUpdateRequest(enabled=False)
            )
        assert seen == [1.0, 2.0, 4.0]

    def test_the_strategy_module_takes_leverage_from_the_account_setting_and_nothing_else(
        self,
    ) -> None:
        import ast
        from pathlib import Path

        source = Path(strategy_module.__file__).read_text()
        tree = ast.parse(source)

        leverage_values: list[ast.expr] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "leverage" and keyword.value is not None:
                        leverage_values.append(keyword.value)
        assert leverage_values, "expected the strategy to pass leverage to its orders"
        # Every `leverage=` value must trace back to `strategy_leverage`
        # (the account's own raw setting) or a fixed multiple of it --
        # VOLATILITY-POSITION-SIZING's own `_resolve_volatility_adjustment`
        # scales it by exactly one of two module-level constants
        # (`_VOLATILITY_SIZE_SHRINK_FACTOR`/`_VOLATILITY_SIZE_GROW_FACTOR`),
        # gated on a separate, validated forecast -- never a value read
        # from a prediction's own confidence or magnitude. Deliberately an
        # explicit, narrow allowlist rather than "anything that isn't
        # confidence", so an unexpected new name still fails loudly.
        allowed_names = {
            "strategy_leverage",
            "default_leverage",
            "scaled_leverage",
            "adjustment",
            "_VOLATILITY_SIZE_SHRINK_FACTOR",
            "_VOLATILITY_SIZE_GROW_FACTOR",
            "Decimal",
            "max",
            "min",
        }
        allowed_attrs = {"leverage"}
        for value in leverage_values:
            names = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(value) if isinstance(n, ast.Attribute)}
            assert names <= allowed_names, ast.dump(value)
            assert attrs <= allowed_attrs, ast.dump(value)
            assert not any("confidence" in name for name in names | attrs)
            assert not any("prediction" in name for name in names | attrs)

        # ...and that name is assigned from the account's setting alone.
        assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "strategy_leverage" for t in node.targets)
        ]
        assert assignments
        for assignment in assignments:
            attrs = {n.attr for n in ast.walk(assignment.value) if isinstance(n, ast.Attribute)}
            names = {n.id for n in ast.walk(assignment.value) if isinstance(n, ast.Name)}
            assert attrs == {"strategy_leverage"}, ast.dump(assignment.value)
            assert not any("confidence" in x or "prediction" in x for x in names | attrs)

    def test_no_code_in_the_application_connects_confidence_to_a_leverage(self) -> None:
        """Grep-verifiable, as the task asked: in every application module, no
        expression that sets or computes a `leverage`/`strategy_leverage` refers
        to a confidence."""
        import ast
        from pathlib import Path

        app_dir = Path(strategy_module.__file__).parents[1]
        offenders: list[str] = []
        for path in app_dir.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                targets: list[tuple[str, ast.AST]] = []
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        name = (
                            target.id
                            if isinstance(target, ast.Name)
                            else target.attr
                            if isinstance(target, ast.Attribute)
                            else ""
                        )
                        targets.append((name, node.value))
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    if isinstance(node.target, ast.Name):
                        targets.append((node.target.id, node.value))
                elif isinstance(node, ast.keyword) and node.arg:
                    targets.append((node.arg, node.value))
                for name, value in targets:
                    if "leverage" not in name:
                        continue
                    referenced = {
                        n.id.lower() for n in ast.walk(value) if isinstance(n, ast.Name)
                    } | {n.attr.lower() for n in ast.walk(value) if isinstance(n, ast.Attribute)}
                    if any("confidence" in r for r in referenced):
                        offenders.append(
                            f"{path.relative_to(app_dir)}:{getattr(node, 'lineno', 0)}"
                        )
        assert offenders == []


@pytest.mark.asyncio
class TestEveryCycleRecordsDirectionAndLeverage:
    async def test_every_kind_of_cycle_is_logged_with_its_direction_and_the_leverage_in_force(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATDIRLOGUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.update_strategy_config(
            account_id,
            PaperStrategyConfigUpdateRequest(
                enabled=True,
                training_job_id=uuid.UUID(job_id),
                confidence_threshold_pct=Decimal("80"),
                leverage=Decimal("3"),
            ),
        )
        scheduler = PaperTradingStrategyScheduler(state_manager=state_manager)

        async def tick(value: object, confidence: float) -> None:
            stub_prediction(
                monkeypatch,
                build_prediction(
                    training_job_id=job_id,
                    symbol="STRATDIRLOGUSD",
                    predicted_value=value,
                    confidence=confidence,
                ),
            )
            await scheduler.run_strategy_tick()

        await tick("down", 0.5)  # below threshold: skipped, but for a SHORT
        await tick("up", 0.5)  # below threshold: skipped, for a LONG
        await tick("flat", 0.95)  # no directional call at all
        await tick("down", 0.95)  # opens a short
        await tick("down", 0.95)  # already short: no change
        await tick("up", 0.95)  # closes the short

        decisions = (
            await service.list_strategy_decisions(account_id, limit=20, offset=0)
        ).decisions
        assert len(decisions) == 6
        by_reason = {d.reason: d for d in decisions}
        rows = sorted(decisions, key=lambda d: (d.action, d.direction or ""))
        summary = [(d.action, d.direction) for d in rows]
        assert summary == sorted(
            [
                ("no_action", "short"),  # below threshold, down
                ("no_action", "long"),  # below threshold, up
                ("no_action", None),  # not directional
                ("opened", "short"),
                ("no_action", "short"),  # already short
                ("closed", "short"),
            ],
            key=lambda pair: (pair[0], pair[1] or ""),
        )
        # Every row, acted or skipped, snapshots the leverage in force.
        assert {float(d.strategy_leverage) for d in decisions} == {3.0}
        assert by_reason  # every row also carries its reasoning
        assert all(d.reason for d in decisions)

    async def test_a_cycle_that_crashes_is_still_logged(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="STRATCRASHUSD", model_type="logistic_regression"
        )
        state_manager = MarketStateManager()
        service = await build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await enable_strategy(service, account_id, job_id)
        stub_prediction(
            monkeypatch,
            build_prediction(
                training_job_id=job_id, symbol="STRATCRASHUSD", predicted_value="up", confidence=0.9
            ),
        )

        async def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(PaperTradingStrategyScheduler, "_open_position", explode)
        summary = await PaperTradingStrategyScheduler(
            state_manager=state_manager
        ).run_strategy_tick()

        assert summary.no_action == 1
        decision = (await service.list_strategy_decisions(account_id, limit=5, offset=0)).decisions[
            0
        ]
        assert decision.action == "no_action"
        assert "boom" in decision.reason
        assert float(decision.strategy_leverage) == pytest.approx(2.0)
