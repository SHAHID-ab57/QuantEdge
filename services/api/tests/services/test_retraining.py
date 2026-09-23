"""Tests for `RetrainingScheduler` (RETRAIN-WITH-MINIMUM-WINDOW).

Mirrors `tests/paper_trading/test_strategy_scheduler.py` and
`tests/services/test_external_data_sync.py`'s own conventions: `get_engine`
monkeypatched to the test's in-memory engine (this scheduler never goes
through `get_db`), and private methods (`_is_due`) exercised directly where
that's the most direct way to prove a pure decision rule.

The two hard floors (`MIN_WINDOW_HOURS`/`MAX_RETRAIN_INTERVAL_SECONDS`) are
tested against their *real* production values in
`TestConstructorEnforcesHardFloors` — nothing there is monkeypatched.
Every other test monkeypatches those two module constants down to toy
values so a full retrain+promote pass can run against a small, fast,
in-memory candle series (mirroring `tests/prediction/test_service.py`'s own
"wobbling, both directions present" real-candle fixture) without waiting on
an 8,760-hour dataset — the floor-enforcement behavior itself doesn't
depend on which numbers are the floor, only that construction refuses to
go below/above it, which the dedicated test above already proves against
the real numbers.

`TestDriftGatesPromotion` is the one that matters most: it proves a fresh
retrain is checked against the drift monitor *before* promotion, on both
branches — a healthy retrain is promoted, and a retrain that reads drifted
against itself (a deliberately narrow window with a final price spike the
fit split never saw, reproducing this task's own root-cause mechanism at
toy scale) is not.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Candle
from app.models.exchange import Exchange
from app.models.market import Market
from app.models.training import TrainingJob
from app.repositories.markets import MarketRepository
from app.schemas.paper_trading import PaperAccountCreateRequest, PaperStrategyConfigUpdateRequest
from app.schemas.training import TrainingJobCreateRequest
from app.services import retraining as retraining_module
from app.services.retraining import (
    MAX_RETRAIN_INTERVAL_SECONDS,
    MIN_WINDOW_HOURS,
    RetrainingScheduler,
    RetrainingTarget,
)
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory
from tests.paper_trading.test_service import build_service
from tests.paper_trading.test_strategy_scheduler import enable_strategy
from tests.prediction.test_service import train_completed_job
from tests.training.test_service import build_service as build_training_service
from tests.training.test_service import seed_experiment_with_real_config


@pytest.fixture(autouse=True)
def _use_test_engine(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr(retraining_module, "get_engine", lambda: engine)


async def seed_final_spike_candle(
    session_factory: SessionFactory,
    *,
    symbol: str,
    spike_price: float = 50_000.0,
) -> None:
    """One more, much later candle at a wildly different price, appended
    after a symbol's wobbling series already exists (from `seed_real_candles`
    via `train_completed_job`) — the toy-scale version of this task's own
    root-cause mechanism: a window whose fit split (the chronologically
    first 70%) never saw the extreme value that shows up in the live/test
    tail."""
    async with session_factory() as session:
        market = await MarketRepository(session).get_by_symbol(symbol)
        assert market is not None
        last = (
            (
                await session.execute(
                    select(Candle)
                    .where(Candle.market_id == market.id)
                    .order_by(Candle.open_time.desc())
                    .limit(1)
                )
            )
            .scalars()
            .one()
        )
        spike_time = last.open_time + timedelta(hours=1)
        session.add(
            Candle(
                market_id=market.id,
                timeframe="1h",
                open_time=spike_time,
                close_time=spike_time + timedelta(hours=1),
                open=Decimal(str(spike_price)),
                high=Decimal(str(spike_price + 10)),
                low=Decimal(str(spike_price - 10)),
                close=Decimal(str(spike_price)),
                volume=Decimal("100"),
                quote_volume=None,
                trade_count=None,
                source="delta",
            )
        )
        await session.commit()


async def _seed_market_and_candles_reusing_exchange(
    session_factory: SessionFactory, *, symbol: str, count: int = 80
) -> None:
    """`seed_real_candles`'s own wobbling-series body, but reusing the
    existing `slug="delta"` exchange instead of unconditionally creating a
    new one — needed only when a test seeds two independent lineages/markets
    in the same in-memory database, where `seed_real_candles`'s own
    `Exchange(...)` call would collide on that unique slug."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with session_factory() as session:
        exchange = (
            (await session.execute(select(Exchange).where(Exchange.slug == "delta")))
            .scalars()
            .first()
        )
        if exchange is None:
            exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
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


async def train_second_lineage_job(
    session_factory: SessionFactory, *, symbol: str, model_type: str
) -> tuple[str, str]:
    """`train_completed_job`'s own body, seeding candles via
    `_seed_market_and_candles_reusing_exchange` instead of
    `seed_real_candles` — for a test that already seeded a first symbol (and
    therefore the shared `slug="delta"` exchange) and needs a second,
    independent lineage in the same in-memory database."""
    await _seed_market_and_candles_reusing_exchange(session_factory, symbol=symbol)
    experiment_id = await seed_experiment_with_real_config(session_factory)
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
        return completed.id, experiment_id
    finally:
        await training_service.repository.session.close()


class TestConstructorEnforcesHardFloors:
    """Against the real, unmonkeypatched production constants — a caller
    cannot build this scheduler with a narrower window or a longer retrain
    gap than the floor, no warn-and-continue path."""

    def test_rejects_a_window_narrower_than_the_floor(self) -> None:
        with pytest.raises(ValueError, match="narrower than the enforced floor"):
            RetrainingScheduler(targets=[], window_hours=MIN_WINDOW_HOURS - 1)

    def test_rejects_a_retrain_interval_longer_than_the_ceiling(self) -> None:
        with pytest.raises(ValueError, match="exceeds the enforced ceiling"):
            RetrainingScheduler(
                targets=[], min_retrain_interval_seconds=MAX_RETRAIN_INTERVAL_SECONDS + 1
            )

    def test_accepts_the_floor_exactly(self) -> None:
        scheduler = RetrainingScheduler(
            targets=[],
            window_hours=MIN_WINDOW_HOURS,
            min_retrain_interval_seconds=MAX_RETRAIN_INTERVAL_SECONDS,
        )
        assert scheduler is not None

    def test_accepts_a_more_conservative_override(self) -> None:
        scheduler = RetrainingScheduler(
            targets=[],
            window_hours=MIN_WINDOW_HOURS * 2,
            min_retrain_interval_seconds=MAX_RETRAIN_INTERVAL_SECONDS // 2,
        )
        assert scheduler is not None


class TestIsDue:
    """`_is_due` is a pure decision rule over a job's own `completed_at` —
    exercised directly, no DB needed."""

    def _scheduler(self) -> RetrainingScheduler:
        return RetrainingScheduler(targets=[])

    def test_a_job_with_no_completed_at_is_due(self) -> None:
        scheduler = self._scheduler()
        job = TrainingJob(completed_at=None)
        assert scheduler._is_due(job, datetime.now(UTC)) is True

    def test_a_recently_completed_job_is_not_due(self) -> None:
        scheduler = self._scheduler()
        now = datetime.now(UTC)
        job = TrainingJob(completed_at=now - timedelta(hours=1))
        assert scheduler._is_due(job, now) is False

    def test_a_job_older_than_the_interval_is_due(self) -> None:
        scheduler = self._scheduler()
        now = datetime.now(UTC)
        job = TrainingJob(completed_at=now - timedelta(seconds=MAX_RETRAIN_INTERVAL_SECONDS + 1))
        assert scheduler._is_due(job, now) is True


@pytest.mark.asyncio
class TestNoCompletedJobYetIsSkippedNotFailed:
    async def test_a_lineage_with_no_completed_job_is_counted_as_not_due(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = uuid.uuid4()
        # No job trained for this experiment at all.
        scheduler = RetrainingScheduler(
            targets=[RetrainingTarget(experiment_id=experiment_id)],
            window_hours=MIN_WINDOW_HOURS,
            min_retrain_interval_seconds=MAX_RETRAIN_INTERVAL_SECONDS,
        )
        summary = await scheduler.run_retraining_tick()

        assert summary.attempted == 1
        assert summary.not_due == 1
        assert summary.retrained == 0
        assert summary.failed == 0


@pytest.mark.asyncio
class TestDriftGatesPromotion:
    async def test_a_healthy_retrain_is_promoted_to_every_enabled_account(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(retraining_module, "MIN_WINDOW_HOURS", 10)
        monkeypatch.setattr(retraining_module, "MAX_RETRAIN_INTERVAL_SECONDS", 1)

        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="RETRAINHEALTHYUSD", model_type="logistic_regression"
        )

        service = await build_service(session_factory, MarketStateManager())
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)

        scheduler = RetrainingScheduler(
            targets=[RetrainingTarget(experiment_id=uuid.UUID(experiment_id))],
            window_hours=80,
            min_retrain_interval_seconds=0,
        )
        summary = await scheduler.run_retraining_tick()

        assert summary.attempted == 1
        assert summary.not_due == 0
        assert summary.retrained == 1
        assert summary.unhealthy == 0
        assert summary.failed == 0
        assert summary.promoted == 1
        assert summary.accounts_repointed == 1

        # The account is now on a genuinely different, newer job.
        refreshed = await service.get_account(uuid.UUID(account.id))
        assert refreshed.strategy_training_job_id is not None
        assert refreshed.strategy_training_job_id != job_id

    async def test_a_self_drifted_retrain_is_not_promoted(
        self,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: list[dict[str, object]] = []
        monkeypatch.setattr(
            retraining_module,
            "capture_retrain_unhealthy",
            lambda **kwargs: captured.append(kwargs),
        )
        monkeypatch.setattr(retraining_module, "MIN_WINDOW_HOURS", 10)
        monkeypatch.setattr(retraining_module, "MAX_RETRAIN_INTERVAL_SECONDS", 1)

        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="RETRAINDRIFTUSD", model_type="logistic_regression"
        )
        # Between the first job and the scheduled retrain, a wild final
        # candle lands — present in the fresh job's own window, but only in
        # its test split, never the fit split.
        await seed_final_spike_candle(session_factory, symbol="RETRAINDRIFTUSD")

        service = await build_service(session_factory, MarketStateManager())
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)

        scheduler = RetrainingScheduler(
            targets=[RetrainingTarget(experiment_id=uuid.UUID(experiment_id))],
            window_hours=40,
            min_retrain_interval_seconds=0,
        )
        summary = await scheduler.run_retraining_tick()

        assert summary.retrained == 1
        assert summary.unhealthy == 1
        assert summary.promoted == 0
        assert summary.accounts_repointed == 0
        assert len(captured) == 1
        assert captured[0]["drift_status"] == "drifted"

        # The account is left exactly where it was — never repointed to an
        # unhealthy job.
        refreshed = await service.get_account(uuid.UUID(account.id))
        assert refreshed.strategy_training_job_id == job_id


@pytest.mark.asyncio
class TestPromotionScopeIsAutoSwap:
    async def test_a_disabled_account_is_never_repointed(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(retraining_module, "MIN_WINDOW_HOURS", 10)
        monkeypatch.setattr(retraining_module, "MAX_RETRAIN_INTERVAL_SECONDS", 1)

        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="RETRAINDISABLEDUSD", model_type="logistic_regression"
        )
        service = await build_service(session_factory, MarketStateManager())
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        # Enabled, then explicitly disabled again — a human opted back out.
        await enable_strategy(service, uuid.UUID(account.id), job_id)
        await service.update_strategy_config(
            uuid.UUID(account.id), PaperStrategyConfigUpdateRequest(enabled=False)
        )

        scheduler = RetrainingScheduler(
            targets=[RetrainingTarget(experiment_id=uuid.UUID(experiment_id))],
            window_hours=80,
            min_retrain_interval_seconds=0,
        )
        summary = await scheduler.run_retraining_tick()

        assert summary.retrained == 1
        assert summary.promoted == 1
        assert summary.accounts_repointed == 0

        refreshed = await service.get_account(uuid.UUID(account.id))
        assert refreshed.strategy_training_job_id == job_id
        assert refreshed.strategy_enabled is False

    async def test_an_account_on_a_different_lineage_is_never_repointed(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(retraining_module, "MIN_WINDOW_HOURS", 10)
        monkeypatch.setattr(retraining_module, "MAX_RETRAIN_INTERVAL_SECONDS", 1)

        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="RETRAINLINEAGEAUSD", model_type="logistic_regression"
        )
        other_job_id, _other_experiment_id = await train_second_lineage_job(
            session_factory, symbol="RETRAINLINEAGEBUSD", model_type="logistic_regression"
        )
        service = await build_service(session_factory, MarketStateManager())
        other_account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(other_account.id), other_job_id)

        scheduler = RetrainingScheduler(
            targets=[RetrainingTarget(experiment_id=uuid.UUID(experiment_id))],
            window_hours=80,
            min_retrain_interval_seconds=0,
        )
        summary = await scheduler.run_retraining_tick()

        assert summary.retrained == 1
        assert summary.accounts_repointed == 0

        refreshed_other = await service.get_account(uuid.UUID(other_account.id))
        assert refreshed_other.strategy_training_job_id == other_job_id


@pytest.mark.asyncio
class TestFailureIsolation:
    async def test_one_targets_failure_never_stops_the_rest(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(retraining_module, "MIN_WINDOW_HOURS", 10)
        monkeypatch.setattr(retraining_module, "MAX_RETRAIN_INTERVAL_SECONDS", 1)

        broken_experiment_id = uuid.uuid4()  # no completed job -> counted not_due, not a crash
        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="RETRAINISOLATIONUSD", model_type="logistic_regression"
        )
        service = await build_service(session_factory, MarketStateManager())
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await enable_strategy(service, uuid.UUID(account.id), job_id)

        scheduler = RetrainingScheduler(
            targets=[
                RetrainingTarget(experiment_id=broken_experiment_id),
                RetrainingTarget(experiment_id=uuid.UUID(experiment_id)),
            ],
            window_hours=80,
            min_retrain_interval_seconds=0,
        )
        summary = await scheduler.run_retraining_tick()

        assert summary.attempted == 2
        assert summary.not_due == 1
        assert summary.retrained == 1
        assert summary.promoted == 1
        assert summary.accounts_repointed == 1
        assert summary.failed == 0
