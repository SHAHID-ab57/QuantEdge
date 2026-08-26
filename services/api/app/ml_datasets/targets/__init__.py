"""Built-in prediction targets, discovered automatically.

Every module in this package is imported on startup, and each one registers
its target via the `@register` decorator at class-definition time — the
same zero-touch discovery mechanism `app/features/builtin/__init__.py`,
`app/indicators/builtin.py`, and `app/dataset_validation/rules/__init__.py`
already use. Adding a target means adding one file here and nothing else.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("app.ml_datasets.targets")

_loaded = False


def load_builtin_targets() -> None:
    """Import every target module in this package exactly once.

    Idempotent, matching every other builtin loader on this platform: any
    entry point may call it defensively without coordinating with others.
    """
    global _loaded
    if _loaded:
        return
    for module_info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{module_info.name}")
        logger.debug("Loaded builtin target module %r", module_info.name)
    _loaded = True
