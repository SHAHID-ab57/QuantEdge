"""Built-in feature generators, discovered automatically.

Every module in this package is imported on startup, and each one registers
its generator via the ``@register`` decorator at class-definition time. The
practical consequence — and the point of the whole design — is that
**adding a hand-written feature means adding one file here and nothing
else**: no pipeline change, no registry edit, no router change, no import
to remember to add. ``test_builtin_discovery`` pins that behaviour.

Moving averages are the exception, and deliberately so: SMA, EMA, and WMA
are registered by *wrapping the existing indicators* rather than by
reimplementing them (see ``indicator_feature.py`` for the full rationale).
That needs the indicator registry loaded first and an engine to delegate
to, so it happens explicitly here rather than through decorator discovery.

The result is that registering a new *indicator* also yields a new feature
for free, once its name is listed in ``INDICATOR_BACKED_FEATURES``.
"""

import importlib
import logging
import pkgutil

from app.features.builtin.indicator_feature import register_indicator_features
from app.features.registry import default_registry
from app.indicators.builtin import load_builtin_indicators
from app.indicators.cache import IndicatorCache
from app.indicators.engine import IndicatorEngine
from app.indicators.registry import default_registry as default_indicator_registry

logger = logging.getLogger("app.features.builtin")

#: Indicators exposed as feature generators. Adding a name here is all it
#: takes to make an already-registered indicator available to datasets.
INDICATOR_BACKED_FEATURES = ("sma", "ema", "wma")

#: Adapter module, not a self-registering generator — skipped by discovery.
_ADAPTER_MODULE = "indicator_feature"

_loaded = False


def load_builtin_features(engine: IndicatorEngine | None = None) -> None:
    """Import every generator module in this package exactly once.

    Idempotent: repeated calls are cheap no-ops, so any entry point (the
    API dependency, a test, a future training job) can call it defensively
    without coordinating with the others — the same contract
    ``load_builtin_indicators`` offers.

    ``engine`` is injectable so the API can share the one process-wide
    ``IndicatorEngine`` (and therefore its result cache) rather than have
    the moving-average features delegate to a second, cold engine.
    """
    global _loaded
    if _loaded:
        return

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name == _ADAPTER_MODULE:
            continue
        importlib.import_module(f"{__name__}.{module_info.name}")
        logger.debug("Loaded builtin feature module %r", module_info.name)

    if engine is None:
        load_builtin_indicators()
        engine = IndicatorEngine(default_indicator_registry, IndicatorCache())

    register_indicator_features(INDICATOR_BACKED_FEATURES, engine, default_registry)
    default_registry.validate_dependencies()
    _loaded = True
