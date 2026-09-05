"""External Data Connectors — the reusable abstraction every external
data source (Delta aside — that integration predates this package and
lives in `app.integrations.delta`) sits on top of.

`load_builtin_connectors()` discovers every connector module in this
package automatically, the same `pkgutil.iter_modules` mechanism
`app.features.builtin.load_builtin_features` already uses: **adding a new
connector means adding one file here and nothing else** — no registry
edit, no scheduler change, no import to remember to add.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("app.connectors")

#: Modules in this package that are not self-registering connectors —
#: skipped by discovery, mirroring `app.features.builtin`'s own
#: `_ADAPTER_MODULE` exclusion.
_NON_CONNECTOR_MODULES = frozenset({"base", "errors", "registry"})

_loaded = False


def load_builtin_connectors() -> None:
    """Import every connector module in this package exactly once.

    Idempotent: repeated calls are cheap no-ops, so any entry point (a
    scheduler, a backfill script, a test) can call it defensively without
    coordinating with the others — the same contract
    `load_builtin_features`/`load_builtin_indicators` already offer.
    """
    global _loaded
    if _loaded:
        return

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name in _NON_CONNECTOR_MODULES:
            continue
        importlib.import_module(f"{__name__}.{module_info.name}")
        logger.debug("Loaded connector module %r", module_info.name)

    _loaded = True
