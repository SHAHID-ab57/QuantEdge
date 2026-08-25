"""Built-in validation rules, discovered automatically.

Every module in this package is imported on startup, and each one registers
its rule via the ``@register`` decorator at class-definition time — the
same zero-touch discovery mechanism ``app/features/builtin/__init__.py``
and ``app/indicators/builtin.py`` already use. The practical consequence:
**adding a rule means adding one file here and nothing else** — no engine
change, no registry edit, no router change, no import to remember to add.
``test_builtin_discovery`` (mirroring the feature engine's own test of the
same name) pins this.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("app.dataset_validation.rules")

_loaded = False


def load_builtin_rules() -> None:
    """Import every rule module in this package exactly once.

    Idempotent: repeated calls are cheap no-ops, so any entry point (the
    API dependency, a test, a future training job) can call it defensively
    without coordinating with the others — the same contract
    ``load_builtin_features``/``load_builtin_indicators`` offer.
    """
    global _loaded
    if _loaded:
        return
    for module_info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{module_info.name}")
        logger.debug("Loaded builtin validation rule module %r", module_info.name)
    _loaded = True
