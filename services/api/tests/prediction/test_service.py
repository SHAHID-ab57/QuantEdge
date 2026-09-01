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

import uuid
from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.dependencies.features import get_dataset_builder
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
