"""Feature Engineering — BC3's engine, registry, pipeline, and dataset builder.

The platform's AI-readiness layer: models consume engineered feature
vectors, not raw candles, and this package is where raw market data becomes
those vectors. See ``ARCHITECTURE.md`` § "Feature Engineering Engine" for
the design and ``docs/ai/AI.md`` for how it fits the wider AI pipeline.

Layered exactly like ``app/indicators/`` — deliberately, so there is one
extension workflow on this platform rather than two — and reusing that
package rather than paralleling it: ``OHLCVPoint`` and ``ParameterSpec``
are imported from it, and the SMA/EMA/WMA features delegate to its engine
instead of reimplementing the maths.
"""

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
    FeatureValue,
)
from app.features.dataset import (
    DatasetFeatureInfo,
    FeatureDataset,
    FeatureDatasetBuilder,
    FeatureRequest,
)
from app.features.pipeline import PIPELINE_VERSION, FeaturePipeline, FeatureRun
from app.features.registry import FeatureRegistry, default_registry, register

__all__ = [
    "PIPELINE_VERSION",
    "DatasetFeatureInfo",
    "FeatureColumn",
    "FeatureContext",
    "FeatureDataset",
    "FeatureDatasetBuilder",
    "FeatureGenerator",
    "FeatureMetadata",
    "FeatureOutput",
    "FeaturePipeline",
    "FeatureRegistry",
    "FeatureRequest",
    "FeatureRun",
    "FeatureSeries",
    "FeatureValue",
    "default_registry",
    "register",
]
