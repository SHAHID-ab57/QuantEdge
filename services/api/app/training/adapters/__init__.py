"""Built-in model adapters, discovered automatically.

Every module in this package is imported on startup, and each one registers
its adapter via the `@register` decorator at class-definition time — the
same zero-touch discovery mechanism `app/ml_datasets/targets/__init__.py`
already uses. Adding a model adapter means adding one file here and nothing
else.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("app.training.adapters")

_loaded = False


def load_builtin_model_adapters() -> None:
    """Import every model adapter module in this package exactly once.

    Idempotent, matching every other builtin loader on this platform: any
    entry point may call it defensively without coordinating with others.
    """
    global _loaded
    if _loaded:
        return
    for module_info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{module_info.name}")
        logger.debug("Loaded builtin model adapter module %r", module_info.name)
    _loaded = True
