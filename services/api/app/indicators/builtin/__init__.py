"""Built-in indicators, discovered automatically.

Every module in this package is imported on startup, and each one registers
its indicator via the ``@register`` decorator at class-definition time. The
practical consequence — and the point of the whole design — is that
**adding an indicator means adding one file here and nothing else**: no
engine change, no registry edit, no router change, no import to remember to
add. ``test_builtin_discovery`` pins that behaviour.

Only three indicators ship today (SMA, EMA, RSI). That is deliberate: they
are reference implementations chosen to cover the three distinct shapes the
contract has to support — a simple window, a recursive/stateful
calculation, and a multi-stage bounded oscillator — so the fourth indicator
anyone writes has a close precedent to copy. This module is the foundation
for hundreds of indicators, not a library of them.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("app.indicators.builtin")

_loaded = False


def load_builtin_indicators() -> None:
    """Import every indicator module in this package exactly once.

    Idempotent: repeated calls are cheap no-ops, so any entry point
    (the API dependency, a test, a future backtest runner) can call it
    defensively without coordinating with the others.
    """
    global _loaded
    if _loaded:
        return
    for module_info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{module_info.name}")
        logger.debug("Loaded builtin indicator module %r", module_info.name)
    _loaded = True
