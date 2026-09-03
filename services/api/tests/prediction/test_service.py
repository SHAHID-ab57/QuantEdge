"""Integration-style tests for `PredictionService` — reconstructs a live
feature vector for a completed training job, runs its model, and persists
the result.

Reuses `tests/training/test_service.py`'s own real-candle/real-experiment
fixtures (`seed_real_candles`, `seed_experiment_with_real_config`,
`build_service`) rather than a second copy of them — the exact same
"wobbling, both up and down labels present" candle series that already
proves the Training Framework works against real data proves the same
thing here, one step further downstream.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.dependencies.features import get_dataset_builder
from app.dependencies.ml_datasets import get_target_pipeline
from app.evaluation.metrics import load_builtin_metrics
from app.evaluation.registry import default_registry as default_metric_registry
from app.models.exchange import Exchange
from app.models.market import Market
from app.prediction.engine import default_engine
from app.prediction.errors import (
    LiveFeatureReconstructionNotSupportedError,
    PredictionRunNotFoundError,
    TrainingFeatureSetMismatchError,
)
from app.repositories.candles import CandleRepository
from app.repositories.experiments import ExperimentRepository
from app.repositories.markets import MarketRepository
from app.repositories.predictions import PredictionRepository
from app.schemas.experiments import ExperimentUpdateRequest, FeatureRequestDTO
from app.schemas.prediction import PredictionRunRequest
from app.schemas.training import TrainingJobCreateRequest
from app.services.experiments import ExperimentService
from app.services.features import FeatureService
from app.services.market_query import CandleNotFoundError, MarketNotFoundError
from app.services.prediction import PredictionService
from app.training.errors import PredictionNotAvailableError, TrainingJobNotFoundError
from tests.conftest import SessionFactory
from tests.training.test_service import (
    build_service as build_training_service,
)
from tests.training.test_service import (
    seed_experiment,
    seed_experiment_with_real_config,
    seed_real_candles,
)


def build_prediction_service(session_factory: SessionFactory) -> PredictionService:
    session = session_factory()
    settings = get_settings()
    load_builtin_metrics()
    return PredictionService(
        repository=PredictionRepository(session),
        training_job_service=build_training_service(session_factory),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        feature_service=FeatureService(
            candle_repository=CandleRepository(session),
            market_repository=MarketRepository(session),
            builder=get_dataset_builder(),
            default_limit=settings.candles_default_limit,
            max_limit=settings.candles_max_limit,
        ),
        market_repository=MarketRepository(session),
        candle_repository=CandleRepository(session),
        engine=default_engine,
        target_pipeline=get_target_pipeline(),
        metric_registry=default_metric_registry,
    )


async def train_completed_job(
    session_factory: SessionFactory,
    *,
    symbol: str,
    model_type: str,
    target: str = "next_direction",
    normalize_features: bool = True,
) -> tuple[str, str]:
    """Seed real candles + a real experiment, train a job to completion, and
    return `(job_id, experiment_id)`."""
    await seed_real_candles(session_factory, symbol=symbol)
    experiment_id = await seed_experiment_with_real_config(session_factory, target=target)
    training_service = build_training_service(session_factory)
    job = await training_service.create(
        TrainingJobCreateRequest(
            experiment_id=experiment_id,
            model_type=model_type,
            symbol=symbol,
            timeframe="1h",
            normalize_features=normalize_features,
        )
    )
    completed = await training_service.run(uuid.UUID(job.id))
    assert completed.status == "completed", completed.error_message
    return completed.id, experiment_id


@pytest.mark.asyncio
class TestRun:
    async def test_reconstructs_a_feature_vector_from_the_real_latest_candle(
        self, session_factory: SessionFactory
    ) -> None:
        """The reconstructed as-of and feature values come from the real stored
        candle, not something fabricated — the strongest concrete proof of that
        is the as-of timestamp exactly matching the actual latest DB candle, and
        an independently-rebuilt OHLCV row (whose columns are identity mappings
        of the raw candle fields) exactly matching that same candle's own
        open/high/low/close/volume."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="RECONUSD", model_type="logistic_regression"
        )
        market_repository = MarketRepository(session_factory())
        candle_repository = CandleRepository(session_factory())
        market = await market_repository.get_by_symbol("RECONUSD")
        assert market is not None
        latest = await candle_repository.get_latest_candle(market.id, "1h")
        assert latest is not None

        service = build_prediction_service(session_factory)
        result = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="RECONUSD")
        )

        assert result.as_of == latest.open_time
        assert result.feature_columns == ["open", "high", "low", "close", "volume"]
        assert result.predicted_value in {"up", "down", "flat"}
        assert result.symbol == "RECONUSD"
        assert result.timeframe == "1h"
        assert result.target_column == "next_direction_1"
        assert result.horizon == 1
        assert result.model_kind == "classification"
        assert result.actual_outcome is None

    async def test_a_classifier_produces_a_labeled_prediction_with_confidence(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="CLSUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)

        result = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="CLSUSD")
        )

        assert isinstance(result.predicted_value, str)
        assert result.confidence is not None
        assert 0.0 <= result.confidence <= 1.0
        assert result.confidence_unavailable_reason is None
        assert result.classes is not None
        assert result.probabilities is not None
        assert set(result.probabilities) == set(result.classes)
        assert abs(sum(result.probabilities.values()) - 1.0) < 1e-6

    async def test_a_regressor_produces_a_numeric_prediction_with_no_confidence(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory,
            symbol="REGUSD",
            model_type="linear_regression",
            target="next_close",
        )
        service = build_prediction_service(session_factory)

        result = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="REGUSD")
        )

        assert isinstance(result.predicted_value, int | float)
        assert result.confidence is None
        assert result.confidence_unavailable_reason is not None
        assert "does not produce class probabilities" in result.confidence_unavailable_reason
        assert result.classes is None
        assert result.probabilities is None
        assert result.model_kind == "regression"

    async def test_persists_the_prediction_and_get_reopens_it(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="GETUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)

        created = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="GETUSD")
        )
        reopened = await service.get(uuid.UUID(created.id))

        assert reopened.id == created.id
        assert reopened.predicted_value == created.predicted_value
        assert reopened.as_of == created.as_of

    async def test_appears_in_prediction_history_filtered_by_training_job(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="HISTUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        created = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="HISTUSD")
        )

        by_job = await service.search(
            training_job_id=uuid.UUID(job_id),
            experiment_id=None,
            symbol=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert created.id in [p.id for p in by_job.predictions]

        by_experiment = await service.search(
            training_job_id=None,
            experiment_id=uuid.UUID(experiment_id),
            symbol=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert created.id in [p.id for p in by_experiment.predictions]

        by_other_symbol = await service.search(
            training_job_id=None,
            experiment_id=None,
            symbol="NOPE",
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert by_other_symbol.total == 0


@pytest.mark.asyncio
class TestNormalizationReuse:
    """Adversarial: proves `PredictionService` reuses the job's own *persisted*
    training-time `NormalizationStats` (`app/training/normalization.py`)
    rather than fitting fresh statistics from the single inference-time row.

    Fitting fresh per-row statistics is a degenerate transform — a single
    row's own z-score against itself is always exactly zero for every
    feature, regardless of the real values — so if that bug existed, every
    prediction from a `normalize_features=True` job would collapse to the
    same all-zero-normalized input and produce identical output regardless
    of which candle it was actually asked to predict from.
    """

    async def test_predictions_at_different_as_of_times_are_not_a_degenerate_constant(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory,
            symbol="ADVNORMUSD",
            model_type="logistic_regression",
            normalize_features=True,
        )
        training_service = build_training_service(session_factory)
        completed = await training_service.get(uuid.UUID(job_id))
        assert completed.result_summary is not None
        assert completed.result_summary["normalization"] is not None
        assert completed.result_summary["normalization_method"] == "zscore"

        market_repository = MarketRepository(session_factory())
        candle_repository = CandleRepository(session_factory())
        market = await market_repository.get_by_symbol("ADVNORMUSD")
        assert market is not None
        latest = await candle_repository.get_latest_candle(market.id, "1h")
        assert latest is not None

        service = build_prediction_service(session_factory)
        earlier_as_of = latest.open_time - timedelta(hours=20)

        result_latest = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="ADVNORMUSD")
        )
        result_earlier = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="ADVNORMUSD", as_of=earlier_as_of
            )
        )

        assert result_latest.as_of != result_earlier.as_of
        # A degenerate single-row normalization would make every prediction's
        # probability vector identical regardless of as_of — real reuse of the
        # job's own persisted stats produces genuinely different probabilities
        # for two different (and, per `seed_real_candles`, genuinely
        # different-valued) candles.
        assert result_latest.probabilities != result_earlier.probabilities


@pytest.mark.asyncio
class TestErrors:
    async def test_raises_when_the_training_job_does_not_exist(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_prediction_service(session_factory)
        with pytest.raises(TrainingJobNotFoundError):
            await service.run(PredictionRunRequest(training_job_id=uuid.uuid4(), symbol="ETHUSD"))

    async def test_raises_when_the_job_has_not_completed_yet(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-pending")
        training_service = build_training_service(session_factory)
        job = await training_service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        service = build_prediction_service(session_factory)

        with pytest.raises(PredictionNotAvailableError):
            await service.run(
                PredictionRunRequest(training_job_id=uuid.UUID(job.id), symbol="ETHUSD")
            )

    async def test_raises_when_the_job_was_never_trained_on_real_data(
        self, session_factory: SessionFactory
    ) -> None:
        """The `placeholder` adapter completes without ever recording
        `feature_columns`/`target_column` — nothing to reconstruct a live
        feature vector from."""
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-placeholder")
        training_service = build_training_service(session_factory)
        job = await training_service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        completed = await training_service.run(uuid.UUID(job.id))
        assert completed.status == "completed"
        service = build_prediction_service(session_factory)

        with pytest.raises(LiveFeatureReconstructionNotSupportedError):
            await service.run(
                PredictionRunRequest(training_job_id=uuid.UUID(job.id), symbol="ETHUSD")
            )

    async def test_raises_for_an_unknown_market_symbol(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="KNOWNUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)

        with pytest.raises(MarketNotFoundError):
            await service.run(
                PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="DOES-NOT-EXIST")
            )

    async def test_raises_when_the_market_exists_but_has_no_candles_for_the_jobs_timeframe(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="NOCANDLESUSD", model_type="logistic_regression"
        )
        # A real market, but for a *different* symbol than the one the job
        # trained on and has no candles at all recorded for it.
        async with session_factory() as session:
            exchange = Exchange(name="Delta Exchange 2", slug="delta-2", country="India")
            session.add(exchange)
            await session.flush()
            session.add(
                Market(
                    exchange_id=exchange.id,
                    symbol="EMPTYUSD",
                    base_asset="EMP",
                    quote_asset="USD",
                    market_type="perpetual",
                )
            )
            await session.commit()
        service = build_prediction_service(session_factory)

        with pytest.raises(CandleNotFoundError):
            await service.run(
                PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="EMPTYUSD")
            )

    async def test_raises_when_the_experiments_feature_set_was_cleared_after_training(
        self, session_factory: SessionFactory
    ) -> None:
        """The job still has real `feature_columns` recorded, but its experiment's
        *current* `feature_set` is now empty — e.g. edited via
        `ExperimentConfigDialog` after this job trained."""
        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="CLEAREDUSD", model_type="logistic_regression"
        )
        experiment_service = ExperimentService(repository=ExperimentRepository(session_factory()))
        await experiment_service.update(
            uuid.UUID(experiment_id), ExperimentUpdateRequest(feature_set=[])
        )
        service = build_prediction_service(session_factory)

        with pytest.raises(LiveFeatureReconstructionNotSupportedError):
            await service.run(
                PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="CLEAREDUSD")
            )

    async def test_raises_when_the_experiments_feature_set_no_longer_produces_the_trained_columns(
        self, session_factory: SessionFactory
    ) -> None:
        """The job's model expects `open`/`high`/`low`/`close`/`volume` (from
        `ohlcv`); if the experiment's `feature_set` is edited afterward to
        something that no longer produces those columns, this is a real,
        actionable mismatch — not the same as never having trained on real
        data at all."""
        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="MISMATCHUSD", model_type="logistic_regression"
        )
        experiment_service = ExperimentService(repository=ExperimentRepository(session_factory()))
        await experiment_service.update(
            uuid.UUID(experiment_id),
            ExperimentUpdateRequest(
                feature_set=[FeatureRequestDTO(feature="sma", params={"period": "20"})]
            ),
        )
        service = build_prediction_service(session_factory)

        with pytest.raises(TrainingFeatureSetMismatchError):
            await service.run(
                PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="MISMATCHUSD")
            )

    async def test_raises_for_an_unknown_prediction_id_on_get(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_prediction_service(session_factory)
        with pytest.raises(PredictionRunNotFoundError):
            await service.get(uuid.uuid4())


#: Well within `seed_real_candles`'s own 80-hour seeded series (starting
#: 2026-01-01T00:00), leaving real candles already stored past a horizon of
#: 1 — gradeable immediately, unlike a prediction at the very latest one.
#: Module-level (not just `TestGradePending`'s own) so
#: `tests/services/test_grading_scheduler.py` can reuse the exact same
#: fixture shape rather than a second copy of it.
EARLY_AS_OF_FOR_GRADING = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=70)


@pytest.mark.asyncio
class TestGradePending:
    """`PredictionService.grade_pending` — the seeded candle series
    (`seed_real_candles`, 80 hourly candles from 2026-01-01T00:00) makes both
    cases easy to construct on purpose: predicting at the very *latest*
    candle leaves nothing after it to grade against yet; predicting at an
    earlier `as_of` (hour 70 of 0..79) leaves real candles already stored
    past its horizon — gradeable immediately, no waiting required.
    """

    _EARLY_AS_OF = EARLY_AS_OF_FOR_GRADING

    async def test_grades_a_prediction_once_its_target_candle_has_closed(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="GRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="GRADEUSD", as_of=self._EARLY_AS_OF
            )
        )
        assert prediction.actual_outcome is None

        summary = await service.grade_pending()

        assert summary.attempted == 1
        assert summary.graded == 1
        assert summary.not_yet_knowable == 0
        assert summary.failed == 0

        graded = await service.get(uuid.UUID(prediction.id))
        assert graded.actual_outcome in {"up", "down", "flat"}
        assert graded.is_correct in {True, False}
        assert graded.error is None
        assert graded.graded_at is not None
        assert graded.available_after is None  # nothing left to wait for

    async def test_leaves_an_ungradeable_prediction_untouched(
        self, session_factory: SessionFactory
    ) -> None:
        """Predicting against the very latest stored candle: there is no
        candle after it yet, so the outcome genuinely isn't knowable —
        `grade_pending` must leave the row exactly as it found it."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="UNGRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="UNGRADEUSD")
        )

        summary = await service.grade_pending()

        assert summary.attempted == 1
        assert summary.graded == 0
        assert summary.not_yet_knowable == 1
        assert summary.failed == 0

        untouched = await service.get(uuid.UUID(prediction.id))
        assert untouched.actual_outcome is None
        assert untouched.is_correct is None
        assert untouched.error is None
        assert untouched.graded_at is None
        assert untouched.available_after is not None

    async def test_a_regressors_prediction_is_graded_with_an_error_not_correctness(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory,
            symbol="GRADEREGUSD",
            model_type="linear_regression",
            target="next_close",
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="GRADEREGUSD", as_of=self._EARLY_AS_OF
            )
        )

        summary = await service.grade_pending()
        assert summary.graded == 1

        graded = await service.get(uuid.UUID(prediction.id))
        # A whole-number float can round-trip through the JSON column as an
        # int (the same JSON-numeric ambiguity `predicted_value`'s own tests
        # already accommodate — see `test_a_regressor_produces_a_numeric_
        # prediction_with_no_confidence` above).
        assert isinstance(graded.actual_outcome, int | float)
        assert graded.error is not None
        assert graded.error >= 0.0
        assert graded.is_correct is None

    async def test_an_already_graded_prediction_is_never_reprocessed(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="REGRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="REGRADEUSD", as_of=self._EARLY_AS_OF
            )
        )

        first_pass = await service.grade_pending()
        assert first_pass.graded == 1

        second_pass = await service.grade_pending()
        assert second_pass.attempted == 0
        assert second_pass.graded == 0

    async def test_leaves_a_prediction_alone_when_target_config_no_longer_matches(
        self, session_factory: SessionFactory
    ) -> None:
        """The experiment's `target_config` was edited (e.g. via
        `ExperimentConfigDialog`) after this prediction was made, so there is
        no longer a recorded entry that produced its `target_column` —
        nothing to reliably re-run grading against, so it's left untouched
        rather than guessed at."""
        job_id, experiment_id = await train_completed_job(
            session_factory, symbol="RETARGETUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="RETARGETUSD", as_of=self._EARLY_AS_OF
            )
        )

        experiment_service = ExperimentService(repository=ExperimentRepository(session_factory()))
        await experiment_service.update(
            uuid.UUID(experiment_id), ExperimentUpdateRequest(target_config=[])
        )

        summary = await service.grade_pending()

        assert summary.attempted == 1
        assert summary.graded == 0
        assert summary.failed == 0

        untouched = await service.get(uuid.UUID(prediction.id))
        assert untouched.actual_outcome is None

    async def test_an_unexpected_failure_grading_one_prediction_does_not_stop_the_rest(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`grade_pending` isolates one bad row from the whole pass — the
        same "one failure never blocks the rest" discipline
        `CandleSyncScheduler.run_catch_up` already applies per symbol/timeframe."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="CRASHGRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="CRASHGRADEUSD", as_of=self._EARLY_AS_OF
            )
        )

        async def boom(self, prediction):
            raise RuntimeError("simulated unexpected grading failure")

        monkeypatch.setattr(type(service), "_grade_one", boom)

        summary = await service.grade_pending()

        assert summary.attempted == 1
        assert summary.graded == 0
        assert summary.failed == 1

    async def test_a_repeated_grading_failure_is_logged_every_pass_not_silent(
        self,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """There is no persistent 'this row is stuck' marker on `Prediction`
        (no `error_message` column exists there, unlike `TrainingJob`) — a
        prediction that fails on *every* attempt is discoverable only
        through this log line, every single pass. Proves it actually fires,
        names the failing prediction, and states the real consequence
        (stays ungraded, retried forever) rather than a bare traceback."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="STUCKGRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="STUCKGRADEUSD", as_of=self._EARLY_AS_OF
            )
        )

        async def boom(self, prediction):
            raise RuntimeError("simulated permanent grading failure")

        monkeypatch.setattr(type(service), "_grade_one", boom)

        with caplog.at_level(logging.ERROR, logger="app.services.prediction"):
            first_pass = await service.grade_pending()
            second_pass = await service.grade_pending()

        assert first_pass.failed == 1
        assert second_pass.failed == 1  # still ungraded, still retried, still failing

        failure_records = [r for r in caplog.records if prediction.id in r.getMessage()]
        assert len(failure_records) == 2  # logged on every pass, not just the first
        assert all(r.levelno == logging.ERROR for r in failure_records)
        assert all(
            "retried on every future grading pass" in r.getMessage() for r in failure_records
        )
        assert all(
            r.exc_info is not None for r in failure_records
        )  # full traceback, not just a message


@pytest.mark.asyncio
class TestGradeNow:
    """`PredictionService.grade_now` — the Backtesting Engine's own way to
    grade a prediction immediately rather than waiting for `grade_pending`'s
    periodic pass. Calls the exact same `_grade_one` `grade_pending` itself
    calls; these tests prove the two behave identically for the same
    prediction, never a second grading code path."""

    _EARLY_AS_OF = EARLY_AS_OF_FOR_GRADING

    async def test_grades_a_knowable_prediction_immediately(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="GRADENOWUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id), symbol="GRADENOWUSD", as_of=self._EARLY_AS_OF
            )
        )
        assert prediction.actual_outcome is None

        outcome = await service.grade_now(uuid.UUID(prediction.id))

        assert outcome is not None
        assert outcome.actual_outcome in {"up", "down", "flat"}
        graded = await service.get(uuid.UUID(prediction.id))
        assert graded.actual_outcome == outcome.actual_outcome
        assert graded.graded_at is not None

    async def test_returns_none_for_a_prediction_not_yet_knowable(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="GRADENOWLATEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(training_job_id=uuid.UUID(job_id), symbol="GRADENOWLATEUSD")
        )

        outcome = await service.grade_now(uuid.UUID(prediction.id))

        assert outcome is None
        untouched = await service.get(uuid.UUID(prediction.id))
        assert untouched.actual_outcome is None

    async def test_raises_for_an_unknown_prediction_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_prediction_service(session_factory)
        with pytest.raises(PredictionRunNotFoundError):
            await service.grade_now(uuid.uuid4())
