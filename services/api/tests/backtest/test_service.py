"""Integration-style tests for `BacktestService` — the two properties this
whole feature exists to guarantee (identical output to a live prediction,
and no look-ahead), plus tagging, aggregation, capping, and error handling.

Reuses `tests/prediction/test_service.py`'s own real-candle/real-experiment
fixtures (`train_completed_job`, `build_prediction_service`) rather than a
second copy of them.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.backtest.errors import (
    BacktestRangeExceedsAvailableDataError,
    BacktestRunNotFoundError,
    InvalidBacktestRangeError,
    InvalidBacktestSortError,
    InvalidBacktestStepError,
)
from app.core.config import get_settings
from app.models.backtest_run import BacktestRun
from app.models.candle import Candle
from app.models.exchange import Exchange
from app.models.market import Market
from app.prediction.errors import LiveFeatureReconstructionNotSupportedError
from app.repositories.backtest_runs import BacktestRunRepository
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.predictions import PredictionFilters, PredictionRepository
from app.schemas.backtest import BacktestRunRequest
from app.schemas.prediction import PredictionRunRequest
from app.schemas.training import TrainingJobCreateRequest
from app.services.backtest import BacktestService
from app.services.market_query import CandleNotFoundError, MarketNotFoundError
from app.services.prediction import PredictionService
from app.training.errors import TrainingJobNotFoundError
from tests.conftest import SessionFactory
from tests.prediction.test_service import (
    build_prediction_service,
    train_completed_job,
)
from tests.training.test_service import (
    build_service as build_training_service,
)
from tests.training.test_service import (
    seed_experiment,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)
#: Well within `seed_real_candles`'s own 80-hour seeded series, leaving real
#: candles already stored past a horizon of 1 for every step walked here.
_EARLY_START = BASE + timedelta(hours=40)


def _utc(value: datetime) -> datetime:
    """Normalize a DB-round-tripped timestamp for comparison against a
    tz-aware literal — the in-memory SQLite test engine discards `tzinfo`
    on write/read even for a `DateTime(timezone=True)` column, the same
    quirk `tests/services/test_candle_ingest.py`'s own helper works around."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def build_backtest_service(
    session_factory: SessionFactory, *, max_steps: int | None = None
) -> BacktestService:
    return BacktestService(
        repository=BacktestRunRepository(session_factory()),
        prediction_service=build_prediction_service(session_factory),
        training_job_service=build_training_service(session_factory),
        max_steps=max_steps if max_steps is not None else get_settings().max_backtest_steps,
    )


@pytest.mark.asyncio
class TestReusesLivePredictionExactly:
    """Objective #1: a backtest step and a live call for the identical
    job/symbol/as_of must produce identical output — proven, not asserted."""

    async def test_a_backtest_step_and_a_live_prediction_produce_identical_output(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTREUSEUSD", model_type="logistic_regression"
        )
        as_of = _EARLY_START

        live_service = build_prediction_service(session_factory)
        live = await live_service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="BTREUSEUSD", as_of=as_of
            )
        )

        backtest_service = build_backtest_service(session_factory)
        run = await backtest_service.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTREUSEUSD",
                start=as_of,
                end=as_of + timedelta(hours=1),
            )
        )
        completed = await backtest_service.execute_run(uuid.UUID(run.id))
        assert completed.status == "completed", completed.error_message

        predictions, total = await PredictionRepository(session_factory()).search(
            PredictionFilters(backtest_run_id=uuid.UUID(run.id)),
            sort="created_at",
            direction="asc",
            limit=10,
            offset=0,
        )
        assert total == 1
        backtest_prediction = predictions[0]

        assert backtest_prediction.as_of == live.as_of
        assert backtest_prediction.predicted_value == live.predicted_value
        assert backtest_prediction.confidence == live.confidence
        assert backtest_prediction.probabilities == live.probabilities
        assert backtest_prediction.classes == live.classes
        assert backtest_prediction.target_column == live.target_column
        assert backtest_prediction.horizon == live.horizon
        assert backtest_prediction.model_kind == live.model_kind


@pytest.mark.asyncio
class TestNoLookAhead:
    """Objective #2: no candle after a step's `as_of` is ever reachable at
    that step — verified adversarially against `PredictionService.run`
    itself (completely unmodified, the exact method the backtest walker
    calls), not re-derived or asserted in prose.
    """

    async def test_removing_every_later_candle_does_not_change_the_prediction(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="NOLOOKAHEADUSD", model_type="logistic_regression"
        )
        as_of = _EARLY_START

        service = build_prediction_service(session_factory)
        with_future_candles = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="NOLOOKAHEADUSD", as_of=as_of
            )
        )

        market = await MarketRepository(session_factory()).get_by_symbol("NOLOOKAHEADUSD")
        assert market is not None
        async with session_factory() as session:
            await session.execute(
                delete(Candle).where(Candle.market_id == market.id, Candle.open_time > as_of)
            )
            await session.commit()

        without_future_candles = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="NOLOOKAHEADUSD", as_of=as_of
            )
        )

        assert without_future_candles.as_of == with_future_candles.as_of
        assert without_future_candles.predicted_value == with_future_candles.predicted_value
        assert without_future_candles.confidence == with_future_candles.confidence
        assert without_future_candles.probabilities == with_future_candles.probabilities


@pytest.mark.asyncio
class TestTaggingAndAggregation:
    async def test_backtest_predictions_are_tagged_and_excluded_from_the_live_history_default(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTTAGUSD", model_type="logistic_regression"
        )
        live_service = build_prediction_service(session_factory)
        live = await live_service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="BTTAGUSD")
        )

        backtest_service = build_backtest_service(session_factory)
        run = await backtest_service.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTTAGUSD",
                start=_EARLY_START,
                end=_EARLY_START + timedelta(hours=3),
            )
        )
        completed = await backtest_service.execute_run(uuid.UUID(run.id))
        assert completed.status == "completed", completed.error_message
        assert completed.total_steps == 3
        assert completed.completed_steps == 3

        repository = PredictionRepository(session_factory())
        default_view, default_total = await repository.search(
            PredictionFilters(), sort="created_at", direction="asc", limit=50, offset=0
        )
        assert default_total == 1  # only the live one — backtest rows excluded by default
        assert [p.id for p in default_view] == [uuid.UUID(live.id)]

        backtest_view, backtest_total = await repository.search(
            PredictionFilters(backtest_run_id=uuid.UUID(run.id)),
            sort="created_at",
            direction="asc",
            limit=50,
            offset=0,
        )
        assert backtest_total == 3
        assert all(p.backtest_run_id == uuid.UUID(run.id) for p in backtest_view)

    async def test_aggregate_metrics_are_populated_from_the_existing_evaluation_engine(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTAGGUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory)
        run = await backtest_service.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTAGGUSD",
                start=_EARLY_START,
                end=_EARLY_START + timedelta(hours=5),
            )
        )

        completed = await backtest_service.execute_run(uuid.UUID(run.id))

        assert completed.status == "completed"
        assert completed.graded_count == 5  # all 5 steps land well before the seeded series ends
        assert completed.aggregate_metrics is not None
        assert "accuracy" in completed.aggregate_metrics
        assert 0.0 <= completed.aggregate_metrics["accuracy"] <= 1.0

    async def test_a_regressors_backtest_aggregates_mae_not_accuracy(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory,
            symbol="BTREGUSD",
            model_type="linear_regression",
            target="next_close",
        )
        backtest_service = build_backtest_service(session_factory)
        run = await backtest_service.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTREGUSD",
                start=_EARLY_START,
                end=_EARLY_START + timedelta(hours=3),
            )
        )

        completed = await backtest_service.execute_run(uuid.UUID(run.id))

        assert completed.status == "completed"
        assert completed.model_kind == "regression"
        assert completed.aggregate_metrics is not None
        assert "mae" in completed.aggregate_metrics
        assert "accuracy" not in completed.aggregate_metrics


@pytest.mark.asyncio
class TestCapping:
    async def test_a_range_needing_more_steps_than_allowed_is_capped_and_reported_honestly(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTCAPUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory, max_steps=3)

        run = await backtest_service.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTCAPUSD",
                start=_EARLY_START,
                end=_EARLY_START + timedelta(hours=10),
            )
        )

        assert run.truncated is True
        assert run.total_steps == 3
        assert _utc(run.effective_end) == _EARLY_START + timedelta(hours=3)
        assert _utc(run.requested_end) == _EARLY_START + timedelta(hours=10)  # the ask, kept


@pytest.mark.asyncio
class TestRangeAgainstAvailableData:
    """A range that reaches past the latest actually-stored candle is
    rejected outright, not silently truncated or run — see
    `BacktestRangeExceedsAvailableDataError`'s own docstring for why
    rejection (not the step-cap's truncate-and-report pattern) is the
    right response here: `PredictionService.run` never interpolates, so
    every step past that point would resolve to the exact same last real
    candle, collapsing into repeated, identical predictions that a
    completed run's own `aggregate_metrics` would otherwise mask as an
    ordinary result. `seed_real_candles` (via `train_completed_job`) always
    stores exactly 80 hourly candles, hours 0..79 — the latest one's own
    coverage runs through hour 80.
    """

    async def test_rejects_a_range_reaching_past_the_latest_stored_candle(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTPASTDATAUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory)

        with pytest.raises(BacktestRangeExceedsAvailableDataError):
            await backtest_service.start(
                BacktestRunRequest(
                    training_job_id=uuid.UUID(job_id),
                    symbol="BTPASTDATAUSD",
                    start=BASE + timedelta(hours=75),
                    end=BASE + timedelta(hours=85),  # past hour 79's own coverage (hour 80)
                )
            )

    async def test_accepts_a_range_ending_exactly_at_the_latest_candles_own_coverage(
        self, session_factory: SessionFactory
    ) -> None:
        """The boundary itself is inclusive, not off-by-one: a range ending
        exactly where the latest candle's own coverage ends (open_time +
        one interval) is genuinely, fully backed by real data — not
        rejected."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTATBOUNDARYUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory)

        run = await backtest_service.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTATBOUNDARYUSD",
                start=BASE + timedelta(hours=75),
                end=BASE + timedelta(hours=80),  # hour 79's own candle covers exactly this
            )
        )

        assert run.status == "running"

    async def test_rejects_when_the_market_has_no_candles_at_all_for_the_jobs_timeframe(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTNOCANDLESUSD", model_type="logistic_regression"
        )
        async with session_factory() as session:
            exchange = Exchange(name="Delta Exchange 2", slug="delta-2", country="India")
            session.add(exchange)
            await session.flush()
            session.add(
                Market(
                    exchange_id=exchange.id,
                    symbol="BTEMPTYUSD",
                    base_asset="EMP",
                    quote_asset="USD",
                    market_type="perpetual",
                )
            )
            await session.commit()
        backtest_service = build_backtest_service(session_factory)

        with pytest.raises(CandleNotFoundError):
            await backtest_service.start(
                BacktestRunRequest(
                    training_job_id=uuid.UUID(job_id),
                    symbol="BTEMPTYUSD",
                    start=_EARLY_START,
                    end=_EARLY_START + timedelta(hours=1),
                )
            )

    async def test_rejects_for_an_unknown_market_symbol(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTKNOWNUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory)

        with pytest.raises(MarketNotFoundError):
            await backtest_service.start(
                BacktestRunRequest(
                    training_job_id=uuid.UUID(job_id),
                    symbol="DOES-NOT-EXIST",
                    start=_EARLY_START,
                    end=_EARLY_START + timedelta(hours=1),
                )
            )


@pytest.mark.asyncio
class TestExecuteRunFailure:
    async def test_a_mid_walk_failure_finalizes_the_whole_run_as_failed_with_partial_progress(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mirrors `TrainingJobService.execute_run`'s own shape: one
        try/except around the *entire* operation, not a per-step
        isolate-and-continue — a step that cannot predict at all means the
        whole run failed, not a silently shorter backtest."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTFAILUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory)
        run = await backtest_service.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTFAILUSD",
                start=_EARLY_START,
                end=_EARLY_START + timedelta(hours=3),
            )
        )

        calls = {"n": 0}
        original_run = PredictionService.run

        async def flaky_run(self: PredictionService, request: PredictionRunRequest):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated mid-backtest failure")
            return await original_run(self, request)

        monkeypatch.setattr(PredictionService, "run", flaky_run)

        completed = await backtest_service.execute_run(uuid.UUID(run.id))

        assert completed.status == "failed"
        assert completed.error_message is not None
        assert "simulated mid-backtest failure" in completed.error_message
        assert completed.completed_steps == 1  # only the first step succeeded


@pytest.mark.asyncio
class TestErrors:
    async def test_raises_when_the_training_job_does_not_exist(
        self, session_factory: SessionFactory
    ) -> None:
        backtest_service = build_backtest_service(session_factory)
        with pytest.raises(TrainingJobNotFoundError):
            await backtest_service.start(
                BacktestRunRequest(
                    training_job_id=uuid.uuid4(),
                    symbol="ETHUSD",
                    start=BASE,
                    end=BASE + timedelta(hours=1),
                )
            )

    async def test_raises_when_the_job_was_never_trained_on_real_data(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-bt-placeholder")
        training_service = build_training_service(session_factory)
        job = await training_service.create(
            TrainingJobCreateRequest(
                experiment_id=uuid.UUID(experiment_id), model_type="placeholder"
            )
        )
        completed = await training_service.run(uuid.UUID(job.id))
        assert completed.status == "completed"

        backtest_service = build_backtest_service(session_factory)
        with pytest.raises(LiveFeatureReconstructionNotSupportedError):
            await backtest_service.start(
                BacktestRunRequest(
                    training_job_id=uuid.UUID(job.id),
                    symbol="ETHUSD",
                    start=BASE,
                    end=BASE + timedelta(hours=1),
                )
            )

    async def test_raises_for_a_step_finer_than_the_jobs_own_timeframe(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTSTEPUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory)
        with pytest.raises(InvalidBacktestStepError):
            await backtest_service.start(
                BacktestRunRequest(
                    training_job_id=uuid.UUID(job_id),
                    symbol="BTSTEPUSD",
                    start=_EARLY_START,
                    end=_EARLY_START + timedelta(hours=1),
                    step="1m",
                )
            )

    async def test_raises_for_an_empty_or_backwards_range(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTRANGEUSD", model_type="logistic_regression"
        )
        backtest_service = build_backtest_service(session_factory)
        with pytest.raises(InvalidBacktestRangeError):
            await backtest_service.start(
                BacktestRunRequest(
                    training_job_id=uuid.UUID(job_id),
                    symbol="BTRANGEUSD",
                    start=_EARLY_START,
                    end=_EARLY_START,
                )
            )

    async def test_raises_for_an_unknown_run_id_on_get(
        self, session_factory: SessionFactory
    ) -> None:
        backtest_service = build_backtest_service(session_factory)
        with pytest.raises(BacktestRunNotFoundError):
            await backtest_service.get(uuid.uuid4())

    async def test_raises_for_an_unsupported_sort_column(
        self, session_factory: SessionFactory
    ) -> None:
        backtest_service = build_backtest_service(session_factory)
        with pytest.raises(InvalidBacktestSortError):
            await backtest_service.search(
                training_job_id=None,
                experiment_id=None,
                symbol=None,
                status_filter=None,
                sort="bogus",
                direction="desc",
                limit=20,
                offset=0,
            )


@pytest.mark.asyncio
class TestConcurrentStart:
    """`POST /backtests/run` has no analog to the check-then-act race
    `TrainingJobService.start` needed closing (`try_transition_to_running`'s
    own atomic `UPDATE ... WHERE status = 'pending'` guard) — not because
    the guard is missing, but because nothing in this feature's own call
    graph ever contends for the same row. A training job's race exists
    because `/training-jobs/{id}/run` acts on one *existing, shared* job id
    that two overlapping requests can both name. `/backtests/run` never
    takes an existing id at all — every call creates a brand-new row, so
    two concurrent calls (even with byte-identical parameters) are exactly
    as independent as two concurrent `POST /predictions/run` calls for the
    same job/symbol: both legitimate, both succeed, neither races the
    other. Both tests below prove this directly rather than asserting it.
    """

    async def test_two_concurrent_identical_requests_each_succeed_as_independent_runs(
        self, session_factory: SessionFactory
    ) -> None:
        """The scenario a duplicate-run guard would need to protect against,
        if one applied here: two overlapping `start()` calls with
        byte-identical parameters, fired via `asyncio.gather` (true
        concurrency, not sequential). Both succeed — this is not "one wins,
        one gets 409" the way training's own race resolved; there is no
        shared resource for either call to lose a race over, since each
        creates and atomically transitions its *own* row.
        """
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTCONCURRENTUSD", model_type="logistic_regression"
        )
        request = BacktestRunRequest(
            training_job_id=uuid.UUID(job_id),
            symbol="BTCONCURRENTUSD",
            start=_EARLY_START,
            end=_EARLY_START + timedelta(hours=1),
        )
        service_a = build_backtest_service(session_factory)
        service_b = build_backtest_service(session_factory)

        result_a, result_b = await asyncio.gather(
            service_a.start(request), service_b.start(request)
        )

        assert result_a.status == "running"
        assert result_b.status == "running"
        assert result_a.id != result_b.id  # two independent rows, never one raced row

        repository = BacktestRunRepository(session_factory())
        row_a = await repository.get_by_id(uuid.UUID(result_a.id))
        row_b = await repository.get_by_id(uuid.UUID(result_b.id))
        assert row_a is not None
        assert row_b is not None
        assert row_a.status == "running"
        assert row_b.status == "running"

    async def test_try_transition_to_running_is_still_atomic_if_ever_raced_directly(
        self, session_factory: SessionFactory
    ) -> None:
        """The guard itself, proven in isolation with the *same* kind of
        test used for training's own race fix — two concurrent transition
        attempts against the identical pre-existing 'pending' row (not two
        separate rows, unlike the test above) — confirming exactly one
        winner. Nothing in `POST /backtests/run`'s own call graph ever
        actually calls `try_transition_to_running` twice on one row (see
        above), but the guard itself, mirrored verbatim from
        `TrainingJobRepository`, is genuinely race-safe if anything ever
        does.
        """
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTRACEGUARDUSD", model_type="logistic_regression"
        )
        run = BacktestRun(
            training_job_id=uuid.UUID(job_id),
            experiment_id=uuid.uuid4(),
            symbol="BTRACEGUARDUSD",
            timeframe="1h",
            step="1h",
            requested_start=_EARLY_START,
            requested_end=_EARLY_START + timedelta(hours=1),
            effective_end=_EARLY_START + timedelta(hours=1),
            truncated=False,
            status="pending",
            total_steps=1,
            completed_steps=0,
            graded_count=0,
            model_kind="classification",
            aggregate_metrics=None,
        )
        created = await BacktestRunRepository(session_factory()).create(run)

        repo_a = BacktestRunRepository(session_factory())
        repo_b = BacktestRunRepository(session_factory())
        result_a, result_b = await asyncio.gather(
            repo_a.try_transition_to_running(created.id),
            repo_b.try_transition_to_running(created.id),
        )

        winners = [result for result in (result_a, result_b) if result is not None]
        assert len(winners) == 1  # exactly one caller ever gets the row back as 'running'


@pytest.mark.asyncio
class TestGradingBoundary:
    """Grading in backtest mode (`PredictionService.grade_now`, reused
    verbatim by `BacktestService.execute_run`) reads only the exact
    `horizon + 1` candles starting at a step's own `as_of` — never
    anything beyond, regardless of how much real data exists further in
    the future. This is a distinct property from `TestNoLookAhead` (above):
    that test covers *feature computation* (`PredictionService.run`'s own
    candle fetch for building the input row); this one covers *grading's*
    own, separate candle fetch (`PredictionService._grade_one`, inside
    `app/services/prediction.py`) for determining the real outcome —
    a different method, a different query, proven here directly rather
    than assumed to inherit the same guarantee.
    """

    async def test_grading_reads_exactly_horizon_plus_one_candles_never_more(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="GRADEBOUNDARYUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        as_of = _EARLY_START  # hour 40; horizon=1 needs hours 40 and 41 only —
        # the seeded series runs to hour 79, so ~38 real candles exist
        # beyond the window this read must never reach.
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="GRADEBOUNDARYUSD", as_of=as_of
            )
        )
        assert prediction.horizon == 1

        captured_kwargs: dict[str, object] = {}
        captured_candles: list[Candle] = []
        original_get_candles = CandleRepository.get_candles

        async def spy_get_candles(self: CandleRepository, market_id, timeframe, **kwargs):
            result = await original_get_candles(self, market_id, timeframe, **kwargs)
            captured_kwargs.clear()
            captured_kwargs.update(kwargs)
            captured_candles.clear()
            captured_candles.extend(result)
            return result

        monkeypatch.setattr(CandleRepository, "get_candles", spy_get_candles)

        outcome = await service.grade_now(uuid.UUID(prediction.id))

        assert outcome is not None  # sanity: grading actually ran, not skipped
        assert captured_kwargs["end"] is None  # no upper-bound WHERE clause...
        assert captured_kwargs["limit"] == prediction.horizon + 1  # ...LIMIT is the only bound
        candles = captured_candles
        assert len(candles) == prediction.horizon + 1  # exactly 2 rows came back, not ~40
        boundary = _utc(as_of) + timedelta(hours=prediction.horizon)
        assert _utc(candles[0].open_time) == _utc(as_of)
        assert _utc(candles[-1].open_time) == boundary
        # The structural guarantee: nothing returned reaches past the
        # boundary, even though ~38 real candles exist after it in the DB.
        assert all(_utc(c.open_time) <= boundary for c in candles)
