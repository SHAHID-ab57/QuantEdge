"""The connector registry — the External Data Connectors context's
extension point, mirroring `app.features.registry.FeatureRegistry`
exactly: nothing that fetches or persists external data ever imports a
concrete connector; both ask the registry for one by source name, which
is what makes "add a connector without modifying the ingestion core"
true rather than aspirational.

One deliberate difference from `FeatureRegistry`: a feature generator is
required to be stateless, so `FeatureRegistry` instantiates it once at
registration time and reuses that instance forever. A connector is not
stateless — it may hold a live, pooled HTTP client — so this registry
registers the *class*, declared metadata included, and builds a fresh
instance only when `get()` is actually called. Registration therefore
stays a side-effect-free import, exactly like every other builtin
discovery on this platform, and the caller that gets a live connector
back owns its lifecycle (mirroring `DeltaClient`'s own explicit
`aclose()`/`async with` contract) instead of an ever-shared instance
requiring internal locking around its own connection pool.
"""

import logging
from typing import TypeVar

from app.connectors.base import Connector, ConnectorMetadata
from app.connectors.errors import ConnectorNotFoundError, DuplicateConnectorError

logger = logging.getLogger("app.connectors.registry")

#: Bound to `Connector` so `register()`/`register_connector()` return the
#: *concrete* decorated class, not the bare `Connector` protocol. Without
#: this, a type checker narrows a `@register_connector`-decorated class
#: down to `type[Connector]` — losing every member the protocol doesn't
#: declare (a connector's own `__init__` kwargs, `__aenter__`/`__aexit__`)
#: and breaking real, correct code at every call site that uses them.
ConnectorT = TypeVar("ConnectorT", bound=Connector)


class ConnectorRegistry:
    """A source → connector-class mapping.

    Instantiable rather than a bare module-level singleton so tests can
    build an isolated registry — the same reason `FeatureRegistry` is.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, type[Connector]] = {}

    def register(self, connector_cls: type[ConnectorT]) -> type[ConnectorT]:
        """Register a connector class. Usable directly as a decorator.

        Returns the class unchanged (both at runtime and, thanks to
        `ConnectorT`, in its static type) so stacking or subclassing still
        works.
        """
        metadata = getattr(connector_cls, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{connector_cls.__name__} must declare a class-level "
                "`metadata: ConnectorMetadata` to be registered"
            )
        source = metadata.source
        if source in self._connectors:
            raise DuplicateConnectorError(source)
        self._connectors[source] = connector_cls
        logger.debug("Registered connector %r (%s)", source, connector_cls.__name__)
        return connector_cls

    def get(self, source: str) -> Connector:
        """Build a fresh connector instance for `source`.

        A fresh instance every call, deliberately — see this module's own
        docstring for why a connector is never a shared singleton the way
        a feature generator is.
        """
        connector_cls = self._connectors.get(source)
        if connector_cls is None:
            raise ConnectorNotFoundError(source, self.names())
        return connector_cls()

    def describe(self, source: str) -> ConnectorMetadata:
        """This connector's own declared metadata, without instantiating it."""
        connector_cls = self._connectors.get(source)
        if connector_cls is None:
            raise ConnectorNotFoundError(source, self.names())
        return connector_cls.metadata

    def has(self, source: str) -> bool:
        """Whether a connector for this source is registered."""
        return source in self._connectors

    def names(self) -> tuple[str, ...]:
        """Every registered source, sorted for a stable catalogue order."""
        return tuple(sorted(self._connectors))

    def describe_all(self) -> list[ConnectorMetadata]:
        """Metadata for every registered connector, sorted by source."""
        return [self._connectors[source].metadata for source in self.names()]

    def __len__(self) -> int:
        return len(self._connectors)

    def __iter__(self):
        return iter(self.names())


#: The registry the application uses. Builtin connectors register into
#: this one at import time (`load_builtin_connectors`), mirroring
#: `app.features.registry.default_registry`.
default_registry = ConnectorRegistry()


def register_connector[T: Connector](connector_cls: type[T]) -> type[T]:
    """Register a connector class into the application's default registry."""
    return default_registry.register(connector_cls)
