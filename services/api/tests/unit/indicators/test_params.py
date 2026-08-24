"""Parameter specification and validation tests.

Validation is the layer that stands between a URL query string and a
calculation, so these tests deliberately pass *strings* in most cases —
that is what the HTTP layer actually delivers.
"""

import pytest

from app.indicators.errors import InvalidIndicatorParameterError
from app.indicators.params import ParameterSpec, validate_parameters


def spec(**overrides: object) -> ParameterSpec:
    """A period-like int spec, overridable per test."""
    base: dict[str, object] = {
        "name": "period",
        "type": "int",
        "label": "Period",
        "description": "Look-back window.",
        "default": 14,
        "minimum": 2,
        "maximum": 100,
    }
    base.update(overrides)
    return ParameterSpec(**base)  # type: ignore[arg-type]


class TestCoercion:
    def test_coerces_a_numeric_string_to_int(self) -> None:
        assert spec().coerce("20") == 20

    def test_coerces_a_numeric_string_to_float(self) -> None:
        parameter = spec(type="float", default=1.0, minimum=None, maximum=None)
        assert parameter.coerce("2.5") == pytest.approx(2.5)

    def test_rejects_a_non_numeric_string(self) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="expected int"):
            spec().coerce("twenty")

    def test_rejects_a_float_string_for_an_int_parameter(self) -> None:
        # int("2.5") raises; silently truncating would change the window size
        # the caller asked for without telling them.
        with pytest.raises(InvalidIndicatorParameterError, match="expected int"):
            spec().coerce("2.5")

    def test_coerces_boolean_strings_both_ways(self) -> None:
        flag = spec(name="smooth", type="bool", default=False, minimum=None, maximum=None)
        assert flag.coerce("true") is True
        assert flag.coerce("0") is False
        assert flag.coerce(True) is True

    def test_rejects_an_unparseable_boolean(self) -> None:
        flag = spec(name="smooth", type="bool", default=False, minimum=None, maximum=None)
        with pytest.raises(InvalidIndicatorParameterError, match="expected a boolean"):
            flag.coerce("maybe")


class TestBounds:
    def test_accepts_values_on_the_inclusive_bounds(self) -> None:
        assert spec().coerce("2") == 2
        assert spec().coerce("100") == 100

    def test_rejects_a_value_below_the_minimum(self) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="must be >= 2, got 1"):
            spec().coerce("1")

    def test_rejects_a_value_above_the_maximum(self) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="must be <= 100, got 101"):
            spec().coerce("101")

    def test_renders_whole_number_bounds_without_a_trailing_decimal(self) -> None:
        parameter = spec(type="float", default=1.0, minimum=0.0, maximum=10.0)
        with pytest.raises(InvalidIndicatorParameterError, match=r"must be >= 0, got -1"):
            parameter.coerce("-1")


class TestChoices:
    def test_accepts_a_declared_choice(self) -> None:
        source = spec(
            name="source",
            type="string",
            default="close",
            minimum=None,
            maximum=None,
            choices=("open", "close"),
        )
        assert source.coerce("open") == "open"

    def test_rejects_a_value_outside_the_choices(self) -> None:
        source = spec(
            name="source",
            type="string",
            default="close",
            minimum=None,
            maximum=None,
            choices=("open", "close"),
        )
        with pytest.raises(InvalidIndicatorParameterError, match="must be one of: open, close"):
            source.coerce("vwap")


class TestRequiredFlag:
    def test_a_spec_without_a_default_is_required(self) -> None:
        assert spec(default=None).required is True

    def test_a_spec_with_a_default_is_optional(self) -> None:
        assert spec(default=14).required is False


class TestValidateParameters:
    def test_fills_in_defaults_for_omitted_parameters(self) -> None:
        resolved = validate_parameters([spec()], {})
        assert resolved == {"period": 14}

    def test_returns_a_complete_map_even_when_partially_supplied(self) -> None:
        source = spec(
            name="source",
            type="string",
            default="close",
            minimum=None,
            maximum=None,
            choices=("open", "close"),
        )
        resolved = validate_parameters([spec(), source], {"period": "9"})
        assert resolved == {"period": 9, "source": "close"}

    def test_rejects_an_unknown_parameter_rather_than_ignoring_it(self) -> None:
        # A typo that silently fell back to the default would produce a
        # plausible-but-wrong number, the worst outcome for research.
        with pytest.raises(InvalidIndicatorParameterError, match="is not accepted"):
            validate_parameters([spec()], {"perid": "9"})

    def test_names_the_accepted_parameters_when_rejecting_an_unknown_one(self) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="it accepts: period"):
            validate_parameters([spec()], {"nope": "1"})

    def test_rejects_a_missing_required_parameter(self) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="is required"):
            validate_parameters([spec(default=None)], {})

    def test_accepts_an_empty_spec_list_with_no_parameters(self) -> None:
        assert validate_parameters([], {}) == {}

    def test_rejects_any_parameter_when_the_indicator_declares_none(self) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="it accepts: none"):
            validate_parameters([], {"period": "5"})
