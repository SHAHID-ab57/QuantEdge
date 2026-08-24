"""Technical Indicator Engine.

A registry-backed execution pipeline for reusable analytical components.
Indicators here are deliberately independent of HTTP, the database, and the
UI — the same implementation serves the REST API today and is intended to
serve replay, backtesting, paper trading, and feature engineering unchanged.

See ``ARCHITECTURE.md`` § "Technical Indicator Engine" for the design and
the workflow for adding a new indicator.
"""

from app.indicators.base import (
    Indicator,
    IndicatorContext,
    IndicatorMetadata,
    IndicatorOutput,
    IndicatorSeries,
    OHLCVPoint,
    SeriesSpec,
)
from app.indicators.cache import IndicatorCache
from app.indicators.engine import IndicatorEngine, IndicatorRun
from app.indicators.errors import (
    DuplicateIndicatorError,
    IndicatorExecutionError,
    IndicatorNotFoundError,
    InsufficientDataError,
    InvalidIndicatorParameterError,
)
from app.indicators.params import ParameterSpec, validate_parameters
from app.indicators.registry import IndicatorRegistry, default_registry, register

__all__ = [
    "DuplicateIndicatorError",
    "Indicator",
    "IndicatorCache",
    "IndicatorContext",
    "IndicatorEngine",
    "IndicatorExecutionError",
    "IndicatorMetadata",
    "IndicatorNotFoundError",
    "IndicatorOutput",
    "IndicatorRegistry",
    "IndicatorRun",
    "IndicatorSeries",
    "InsufficientDataError",
    "InvalidIndicatorParameterError",
    "OHLCVPoint",
    "ParameterSpec",
    "SeriesSpec",
    "default_registry",
    "register",
    "validate_parameters",
]
