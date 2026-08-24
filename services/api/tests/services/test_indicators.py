"""IndicatorService tests — the join between stored candles and the engine.

Exercises the service against the in-memory SQLite database used by the
rest of the suite, so the ORM → ``OHLCVPoint`` projection and the shared
market/timeframe/range validation are covered against real rows rather
than mocks.
"""

import pytest

from app.indicators.builtin import load_builtin_indicators
from app.indicators.cache import IndicatorCache
from app.indicators.engine import IndicatorEngine
from app.indicators.errors import IndicatorNotFoundError, InsufficientDataError
from app.indicators.registry import default_registry
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.schemas.indicators import IndicatorBatchItemRequest
from app.services.indicators import IndicatorService
from app.services.market_query import (
    CandleNotFoundError,
    InvalidRangeError,
    InvalidTimeframeError,
    LimitExceededError,
    MarketNotFoundError,
)
from tests.conftest import SessionFactory, utc


def build_service(session_factory: SessionFactory, *, cached: bool = False) -> IndicatorService:
    """An IndicatorService over the test database and the real registry."""
    load_builtin_indicators()
    session = session_factory()
    engine = IndicatorEngine(default_registry, IndicatorCache() if cached else None)
    return IndicatorService(
        candle_repository=CandleRepository(session),
        market_repository=MarketRepository(session),
        engine=engine,
        default_limit=100,
        max_limit=1000,
    )


class TestCatalogue:
    def test_lists_every_registered_indicator(self, session_factory: SessionFactory) -> None:
        catalogue = build_service(session_factory).list_indicators()
        names = {entry.name for entry in catalogue.indicators}
        assert {"sma", "ema", "wma", "rsi"} <= names
        assert catalogue.total == len(catalogue.indicators)

    def test_reports_the_distinct_categories_present(self, session_factory: SessionFactory) -> None:
        catalogue = build_service(session_factory).list_indicators()
        assert "trend" in catalogue.categories
        assert catalogue.categories == sorted(catalogue.categories)

    def test_publishes_parameter_specs_a_ui_can_build_a_form_from(
        self, session_factory: SessionFactory
    ) -> None:
        sma = build_service(session_factory).get_indicator("sma")
        period = next(spec for spec in sma.parameters if spec.name == "period")
        assert period.type == "int"
        assert period.default == 20
        assert period.minimum == 1
        assert period.required is False

    def test_raises_for_an_unknown_indicator(self, session_factory: SessionFactory) -> None:
        with pytest.raises(IndicatorNotFoundError):
            build_service(session_factory).get_indicator("nope")

    def test_publishes_engineering_metadata_for_every_indicator(
        self, session_factory: SessionFactory
    ) -> None:
        sma = build_service(session_factory).get_indicator("sma")
        assert sma.version
        assert sma.author
        assert sma.complexity
        assert sma.warmup_description == "Equal to the period parameter."

    def test_publishes_search_aliases(self, session_factory: SessionFactory) -> None:
        sma = build_service(session_factory).get_indicator("sma")
        assert "MA" in sma.aliases
        rsi = build_service(session_factory).get_indicator("rsi")
        assert "Relative Strength" in rsi.aliases


class TestCalculation:
    async def test_calculates_over_stored_candles(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # seeded_varied: three ETCUSD 1h candles with closes 11, 24, 32.
        service = build_service(session_factory)
        result = await service.calculate("ETCUSD", "sma", timeframe="1h", params={"period": "2"})
        assert [round(v, 4) if v is not None else None for v in result.series[0].values] == [
            None,
            17.5,
            28.0,
        ]

    async def test_aligns_timestamps_with_every_series(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        result = await service.calculate("ETCUSD", "sma", timeframe="1h", params={"period": "2"})
        assert len(result.timestamps) == 3
        assert result.timestamps[0] == utc(0)
        for series in result.series:
            assert len(series.values) == len(result.timestamps)

    async def test_reports_the_resolved_parameters_including_defaults(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        result = await service.calculate("ETCUSD", "sma", timeframe="1h", params={"period": "2"})
        assert result.parameters == {"period": 2, "source": "close"}

    async def test_calculates_correctly_when_optional_candle_fields_are_null(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # `seeded_varied` candles carry quote_volume=None and
        # trade_count=None (both nullable in the schema) — the ORM →
        # OHLCVPoint projection must never read them, so a calculation
        # must succeed identically whether or not they're populated.
        service = build_service(session_factory)
        result = await service.calculate("ETCUSD", "sma", timeframe="1h", params={"period": "2"})
        assert result.series[0].values == [None, pytest.approx(17.5), pytest.approx(28.0)]

    async def test_reports_calculation_metadata(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        result = await service.calculate("ETCUSD", "sma", timeframe="1h", params={"period": "2"})
        assert result.meta.candles_analyzed == 3
        assert result.meta.warmup_candles == 2
        assert result.meta.cache_status == "disabled"
        assert result.meta.database_time_ms >= 0.0

    async def test_reports_a_cache_hit_on_an_identical_repeat_request(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory, cached=True)
        first = await service.calculate("ETCUSD", "sma", timeframe="1h", params={"period": "2"})
        second = await service.calculate("ETCUSD", "sma", timeframe="1h", params={"period": "2"})
        assert first.meta.cache_status == "miss"
        assert second.meta.cache_status == "hit"
        assert second.series[0].values == first.series[0].values

    async def test_honours_an_explicit_limit(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        # `seeded` has five ETHUSD 1h candles.
        service = build_service(session_factory)
        result = await service.calculate(
            "ETHUSD", "sma", timeframe="1h", params={"period": "1"}, limit=3
        )
        assert result.meta.candles_analyzed == 3


class TestValidation:
    async def test_rejects_an_unknown_market(self, session_factory: SessionFactory) -> None:
        with pytest.raises(MarketNotFoundError):
            await build_service(session_factory).calculate("NOPE", "sma", timeframe="1h", params={})

    async def test_rejects_an_unsupported_timeframe(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(InvalidTimeframeError):
            await build_service(session_factory).calculate(
                "ETHUSD", "sma", timeframe="7d", params={}
            )

    async def test_rejects_a_half_specified_range(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(InvalidRangeError, match="together"):
            await build_service(session_factory).calculate(
                "ETHUSD", "sma", timeframe="1h", params={}, start=utc(0)
            )

    async def test_rejects_a_limit_above_the_configured_maximum(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(LimitExceededError):
            await build_service(session_factory).calculate(
                "ETHUSD", "sma", timeframe="1h", params={}, limit=5000
            )

    async def test_rejects_an_unknown_indicator(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        with pytest.raises(IndicatorNotFoundError):
            await build_service(session_factory).calculate(
                "ETHUSD", "nope", timeframe="1h", params={}
            )

    async def test_raises_when_no_candles_are_stored(
        self, session_factory: SessionFactory, seeded: None
    ) -> None:
        # A market that exists, on a timeframe with nothing stored.
        with pytest.raises(CandleNotFoundError):
            await build_service(session_factory).calculate(
                "ETHUSD", "sma", timeframe="1d", params={}
            )

    async def test_raises_when_the_range_is_shorter_than_the_warmup(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # Three candles stored, but the default SMA period is 20.
        with pytest.raises(InsufficientDataError) as exc_info:
            await build_service(session_factory).calculate(
                "ETCUSD", "sma", timeframe="1h", params={}
            )
        assert exc_info.value.required == 20
        assert exc_info.value.available == 3


class TestBatchCalculation:
    """The chart overlay API: several indicators, one shared candle load."""

    async def test_calculates_every_requested_indicator(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.calculate_batch(
            "ETCUSD",
            timeframe="1h",
            requests=[
                IndicatorBatchItemRequest(indicator="sma", params={"period": "2"}),
                IndicatorBatchItemRequest(indicator="ema", params={"period": "2"}),
            ],
        )
        assert response.symbol == "ETCUSD"
        assert len(response.results) == 2
        assert all(item.success for item in response.results)
        assert response.results[0].series[0].values == [
            None,
            pytest.approx(17.5),
            pytest.approx(28.0),
        ]

    async def test_reports_batch_level_metadata(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.calculate_batch(
            "ETCUSD",
            timeframe="1h",
            requests=[IndicatorBatchItemRequest(indicator="sma", params={"period": "2"})],
        )
        assert response.candles_analyzed == 3
        assert response.database_time_ms >= 0.0
        assert response.engine_version
        assert response.generated_at is not None

    async def test_reports_per_item_warmup_and_execution_time(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.calculate_batch(
            "ETCUSD",
            timeframe="1h",
            requests=[IndicatorBatchItemRequest(indicator="sma", params={"period": "2"})],
        )
        item = response.results[0]
        assert item.warmup_candles == 2
        assert item.execution_time_ms is not None
        assert item.execution_time_ms >= 0.0

    async def test_shares_one_timestamps_array_across_every_result(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.calculate_batch(
            "ETCUSD",
            timeframe="1h",
            requests=[
                IndicatorBatchItemRequest(indicator="sma", params={"period": "2"}),
                IndicatorBatchItemRequest(indicator="ema", params={"period": "2"}),
            ],
        )
        assert len(response.timestamps) == 3
        for item in response.results:
            assert len(item.series[0].values) == len(response.timestamps)

    async def test_one_bad_indicator_does_not_fail_the_others(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        response = await service.calculate_batch(
            "ETCUSD",
            timeframe="1h",
            requests=[
                IndicatorBatchItemRequest(indicator="sma", params={"period": "2"}),
                IndicatorBatchItemRequest(indicator="nope", params={}),
                IndicatorBatchItemRequest(indicator="sma", params={"period": "0"}),
            ],
        )
        assert response.results[0].success is True
        assert response.results[1].success is False
        assert response.results[1].error_code == "indicator_not_found"
        assert response.results[2].success is False
        assert response.results[2].error_code == "invalid_indicator_parameter"

    async def test_reports_a_cache_hit_on_a_repeated_batch(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # Batching doesn't bypass the engine's own result cache: an
        # identical second batch must report a hit per item, the same
        # guarantee the single-indicator endpoint gives.
        service = build_service(session_factory, cached=True)
        item = IndicatorBatchItemRequest(indicator="sma", params={"period": "2"})
        first = await service.calculate_batch("ETCUSD", timeframe="1h", requests=[item])
        second = await service.calculate_batch("ETCUSD", timeframe="1h", requests=[item])
        assert first.results[0].cache_status == "miss"
        assert second.results[0].cache_status == "hit"
        assert second.results[0].series == first.results[0].series

    async def test_raises_for_an_unknown_market_before_running_anything(
        self, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(MarketNotFoundError):
            await build_service(session_factory).calculate_batch(
                "NOPE",
                timeframe="1h",
                requests=[IndicatorBatchItemRequest(indicator="sma", params={})],
            )

    async def test_raises_for_an_unsupported_timeframe_before_running_anything(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        with pytest.raises(InvalidTimeframeError):
            await build_service(session_factory).calculate_batch(
                "ETCUSD",
                timeframe="7d",
                requests=[IndicatorBatchItemRequest(indicator="sma", params={})],
            )

    async def test_raises_when_no_candles_are_stored(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        with pytest.raises(CandleNotFoundError):
            await build_service(session_factory).calculate_batch(
                "ETCUSD",
                timeframe="1d",
                requests=[IndicatorBatchItemRequest(indicator="sma", params={})],
            )
