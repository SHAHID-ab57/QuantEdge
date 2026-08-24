"""Tests for the shared moving-average utilities.

These exist independently of any specific indicator so a change to the
shared factories can't hide behind SMA/EMA/WMA's own tests passing for
unrelated reasons.
"""

from app.indicators.base import IndicatorOutput
from app.indicators.builtin.common import (
    PRICE_SOURCES,
    period_parameter,
    period_warmup,
    single_series_output,
    source_parameter,
)


class TestPeriodParameter:
    def test_builds_a_period_spec_with_the_given_description(self) -> None:
        spec = period_parameter(description="Window size.")
        assert spec.name == "period"
        assert spec.type == "int"
        assert spec.label == "Period"
        assert spec.description == "Window size."

    def test_applies_sensible_defaults(self) -> None:
        spec = period_parameter(description="Window size.")
        assert spec.default == 20
        assert spec.minimum == 1
        assert spec.maximum == 1000

    def test_allows_overriding_the_defaults(self) -> None:
        spec = period_parameter(description="Window size.", default=14, minimum=2, maximum=500)
        assert spec.default == 14
        assert spec.minimum == 2
        assert spec.maximum == 500


class TestSourceParameter:
    def test_builds_a_source_spec_constrained_to_price_fields(self) -> None:
        spec = source_parameter()
        assert spec.name == "source"
        assert spec.type == "string"
        assert spec.choices == PRICE_SOURCES
        assert spec.default == "close"

    def test_allows_a_custom_description(self) -> None:
        spec = source_parameter(description="Which price to smooth.")
        assert spec.description == "Which price to smooth."


class TestPeriodWarmup:
    def test_reads_the_period_parameter(self) -> None:
        assert period_warmup({"period": 20}) == 20

    def test_coerces_a_string_period(self) -> None:
        # Defensive: params are normally already coerced by the engine, but
        # this helper shouldn't silently misbehave if called earlier.
        assert period_warmup({"period": "14"}) == 14


class TestSingleSeriesOutput:
    def test_wraps_one_series_with_the_given_name_and_label(self) -> None:
        output = single_series_output("sma", "SMA(20)", [None, 1.0, 2.0])
        assert isinstance(output, IndicatorOutput)
        assert len(output.series) == 1
        assert output.series[0].name == "sma"
        assert output.series[0].label == "SMA(20)"
        assert output.series[0].values == [None, 1.0, 2.0]
