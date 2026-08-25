"""FeatureService tests — the join between stored candles and the engine.

Exercises the service against the in-memory SQLite database the rest of the
suite uses, so the ORM → ``OHLCVPoint`` projection and the shared
market/timeframe/range validation are covered against real rows rather than
mocks.
"""

import pytest

from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDatasetBuilder
from app.features.errors import FeatureNotFoundError
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.schemas.features import FeatureDatasetRequest, FeatureRequestItem
from app.services.features import FeatureService
from app.services.market_query import (
    CandleNotFoundError,
    InvalidRangeError,
    InvalidTimeframeError,
    LimitExceededError,
    MarketNotFoundError,
)
from tests.conftest import SessionFactory, utc


def build_service(session_factory: SessionFactory) -> FeatureService:
    """A FeatureService over the test database and the real registry."""
    load_builtin_features()
    session = session_factory()
    return FeatureService(
        candle_repository=CandleRepository(session),
        market_repository=MarketRepository(session),
        builder=FeatureDatasetBuilder(FeaturePipeline(default_registry)),
        default_limit=100,
        max_limit=1000,
    )


def request(*items: FeatureRequestItem, **kwargs: object) -> FeatureDatasetRequest:
    """A dataset request over 1h candles with sensible defaults."""
    payload: dict[str, object] = {"timeframe": "1h", "features": list(items)}
    payload.update(kwargs)
    return FeatureDatasetRequest(**payload)  # type: ignore[arg-type]


def item(feature: str, **params: str) -> FeatureRequestItem:
    return FeatureRequestItem(feature=feature, params=dict(params))


class TestCatalogue:
    def test_lists_every_registered_generator(self, session_factory: SessionFactory) -> None:
        catalogue = build_service(session_factory).list_features()
        names = {entry.name for entry in catalogue.features}
        assert {"ohlcv", "candle_shape", "sma", "ema", "wma"} <= names
        assert catalogue.total == len(catalogue.features)

    def test_reports_the_distinct_categories_present(self, session_factory: SessionFactory) -> None:
        catalogue = build_service(session_factory).list_features()
        assert "raw" in catalogue.categories
        assert "price_action" in catalogue.categories
        assert catalogue.categories == sorted(catalogue.categories)

    def test_publishes_parameter_specs_a_ui_can_build_a_form_from(
        self, session_factory: SessionFactory
    ) -> None:
        sma = build_service(session_factory).get_feature("sma")
        period = next(spec for spec in sma.parameters if spec.name == "period")
        assert period.type == "int"
        assert period.default == 20
        assert period.minimum == 1
        assert period.required is False

    def test_publishes_engineering_metadata(self, session_factory: SessionFactory) -> None:
        shape = build_service(session_factory).get_feature("candle_shape")
        assert shape.version
        assert shape.author
        assert shape.complexity
        assert shape.outputs

    def test_raises_for_an_unknown_generator(self, session_factory: SessionFactory) -> None:
        with pytest.raises(FeatureNotFoundError):
            build_service(session_factory).get_feature("nope")


class TestDatasetBuilding:
    async def test_builds_a_dataset_over_stored_candles(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # seeded_varied: three ETCUSD 1h candles, closes 11, 24, 32.
        service = build_service(session_factory)
        response = await service.build_dataset("ETCUSD", request(item("ohlcv")))
        assert response.symbol == "ETCUSD"
        assert [column.name for column in response.columns] == [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        assert response.meta.row_count == 3

    async def test_rows_align_with_timestamps(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.build_dataset("ETCUSD", request(item("ohlcv")))
        assert len(response.timestamps) == len(response.rows)
        assert response.timestamps[0] == utc(0)

    async def test_combines_several_features(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.build_dataset(
            "ETCUSD", request(item("ohlcv"), item("candle_shape"), item("sma", period="2"))
        )
        names = [column.name for column in response.columns]
        assert "close" in names
        assert "candle_body" in names
        assert "sma_2" in names

    async def test_delegated_moving_average_matches_the_indicator(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # closes 11, 24, 32 → SMA(2) = [null, 17.5, 28.0]; after warmup
        # trimming the two defined values remain.
        service = build_service(session_factory)
        response = await service.build_dataset("ETCUSD", request(item("sma", period="2")))
        assert [row[0] for row in response.rows] == [pytest.approx(17.5), pytest.approx(28.0)]

    async def test_reports_dataset_provenance(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.build_dataset("ETCUSD", request(item("sma", period="2")))
        assert response.meta.pipeline_version
        assert response.meta.candles_analyzed == 3
        assert response.meta.rows_dropped == 1
        assert response.meta.warmup_candles == 2
        assert response.meta.database_time_ms >= 0.0
        assert response.features[0].parameters == {"period": 2, "source": "close"}

    async def test_keeps_warmup_rows_when_asked(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.build_dataset(
            "ETCUSD", request(item("sma", period="2"), drop_warmup=False)
        )
        assert response.meta.row_count == 3
        assert response.rows[0][0] is None

    async def test_widens_the_candle_window_by_the_warmup(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        # `seeded` has five ETHUSD 1h candles. Asking for 3 rows with an
        # SMA(2) must return 3 rows, not 3 minus the warmup — otherwise
        # adding a longer-period feature would silently shrink a dataset.
        service = build_service(session_factory)
        response = await service.build_dataset("ETHUSD", request(item("sma", period="2"), limit=3))
        assert response.meta.row_count == 3

    async def test_truncates_for_preview_without_hiding_the_true_size(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        # A preview must never be mistakable for the whole dataset.
        service = build_service(session_factory)
        response = await service.build_dataset("ETHUSD", request(item("ohlcv"), preview_rows=2))
        assert response.meta.row_count == 2
        assert len(response.rows) == 2
        assert response.meta.total_rows == 5
        assert response.meta.truncated is True

    async def test_reports_untruncated_when_everything_fits(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.build_dataset("ETCUSD", request(item("ohlcv"), preview_rows=100))
        assert response.meta.truncated is False
        assert response.meta.total_rows == response.meta.row_count


class TestValidation:
    async def test_rejects_an_unknown_market(self, session_factory: SessionFactory) -> None:
        with pytest.raises(MarketNotFoundError):
            await build_service(session_factory).build_dataset("NOPE", request(item("ohlcv")))

    async def test_rejects_an_unsupported_timeframe(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(InvalidTimeframeError):
            await build_service(session_factory).build_dataset(
                "ETHUSD", request(item("ohlcv"), timeframe="7d")
            )

    async def test_rejects_a_half_specified_range(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(InvalidRangeError, match="together"):
            await build_service(session_factory).build_dataset(
                "ETHUSD", request(item("ohlcv"), start=utc(0))
            )

    async def test_rejects_a_limit_above_the_configured_maximum(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(LimitExceededError):
            await build_service(session_factory).build_dataset(
                "ETHUSD", request(item("ohlcv"), limit=5000)
            )

    async def test_records_an_unknown_feature_as_a_quality_failure(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        response = await build_service(session_factory).build_dataset(
            "ETHUSD", request(item("nope"))
        )
        assert response.columns == []
        assert response.quality.feature_failures[0].error_code == "feature_not_found"

    async def test_raises_when_no_candles_are_stored(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(CandleNotFoundError):
            await build_service(session_factory).build_dataset(
                "ETHUSD", request(item("ohlcv"), timeframe="1d")
            )

    async def test_records_a_range_shorter_than_the_warmup_as_a_quality_failure(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # Three candles stored, default SMA period of 20 — a per-feature
        # outcome now, not a whole-request failure (see
        # FeatureDatasetBuilder.build's partial-success contract).
        response = await build_service(session_factory).build_dataset(
            "ETCUSD", request(item("sma"))
        )
        assert response.columns == []
        failure = response.quality.feature_failures[0]
        assert failure.feature == "sma"
        assert failure.error_code == "insufficient_data"

    async def test_one_failing_feature_does_not_block_the_others(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        response = await build_service(session_factory).build_dataset(
            "ETCUSD", request(item("ohlcv"), item("sma"))
        )
        assert [c.name for c in response.columns] == [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        assert response.quality.feature_failures[0].feature == "sma"


class TestExport:
    async def test_exports_csv_with_a_filename_and_media_type(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        exported = await service.export_dataset("ETCUSD", request(item("ohlcv")), "csv")
        assert exported.media_type.startswith("text/csv")
        assert exported.filename.endswith(".csv")
        assert "timestamp,open,high,low,close,volume" in exported.content

    async def test_exports_json_with_a_filename_and_media_type(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        exported = await service.export_dataset("ETCUSD", request(item("ohlcv")), "json")
        assert exported.media_type.startswith("application/json")
        assert exported.filename.endswith(".json")
        assert '"symbol": "ETCUSD"' in exported.content

    async def test_export_ignores_preview_truncation(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        # The single most damaging thing an export could do is ship only
        # what the preview happened to show.
        service = build_service(session_factory)
        exported = await service.export_dataset(
            "ETHUSD", request(item("ohlcv"), preview_rows=1), "csv"
        )
        data_rows = [
            line
            for line in exported.content.splitlines()
            if not line.startswith("#") and not line.startswith("timestamp")
        ]
        assert len(data_rows) == 5

    async def test_export_validates_the_same_way_a_build_does(
        self, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(MarketNotFoundError):
            await build_service(session_factory).export_dataset(
                "NOPE", request(item("ohlcv")), "csv"
            )
