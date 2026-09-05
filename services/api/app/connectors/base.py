"""The external data connector contract: a date range in, raw data points out.

The :class:`Connector` protocol is the extension point for every future
external data source (Marketaux, Etherscan, FRED, DefiLlama —
`docs/architecture/SystemContext.md` § 3) — mirroring
`app.marketdata.normalizer.Normalizer`'s own role as the extension point
for future exchanges: implement `fetch()`, declare `metadata`, and
register via `app.connectors.registry.register_connector`. Nothing else
on this platform needs to change to support a new source.

Deliberately narrow: a connector only ever fetches and shapes data. It
never touches the database (that's `app.services.external_data_ingest`'s
job, mirroring `app.services.candle_ingest`'s own split between "fetch
and validate" and "persist") and never knows about features or datasets
(that's `app.features.builtin.fear_greed`'s job) — the same
framework/database-free layering `app.features.base`'s own module
docstring already establishes for feature generators, applied here to
connectors instead.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Protocol

__all__ = [
    "Connector",
    "ConnectorMetadata",
    "RawDataPoint",
]


@dataclass(frozen=True, slots=True)
class RawDataPoint:
    """One external data point exactly as a connector reports it.

    `symbol` is `None` for a source-wide/global value — Fear & Greed has
    no per-market variant, unlike a future connector (e.g. Etherscan gas
    fees) that might report one value per chain/asset. `raw_payload` is
    the connector's own untouched record for this point, kept for audit
    and debugging — never re-parsed by anything downstream.
    """

    timestamp: datetime
    value: float
    symbol: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ConnectorMetadata:
    """Everything the catalogue knows about a connector without running it.

    Deliberately the same shape family as `FeatureMetadata`/
    `IndicatorMetadata`: a client that can already render one catalogue
    can render this one with no new code.
    """

    source: str
    label: str
    description: str
    #: Free-form update cadence this source actually publishes at, e.g.
    #: `"daily"` — documents intent for a scheduler/backfill script to read;
    #: not machine-enforced anywhere.
    frequency: str = ""
    requires_auth: bool = False
    version: str = "1.0.0"
    aliases: tuple[str, ...] = field(default_factory=tuple)


class Connector(Protocol):
    """External data source adapter: fetch a range, get raw data points back.

    `metadata` is a `ClassVar` (mirroring `FeatureGenerator.metadata`) so
    the registry can read it off the class itself, before any instance
    exists — the same reason `ConnectorRegistry.register` instantiates the
    class only when a caller actually needs a working connector (`get`),
    never eagerly at registration time: a connector may hold a live HTTP
    client, and registration must stay a cheap, side-effect-free import.
    """

    metadata: ClassVar[ConnectorMetadata]

    async def fetch(self, start: datetime, end: datetime) -> Sequence[RawDataPoint]:
        """Fetch every data point this source has in `[start, end]` (inclusive
        both ends — an external data source's own cadence is coarse enough,
        daily or slower, that a half-open range would risk silently excluding
        an edge value the half-open convention `Candle`'s own `open_time`
        range uses doesn't have to worry about at candle granularity).

        Returns points in whatever order the source provides; ordering
        into chronological order is the ingestion layer's job, not the
        connector's. Raises a `ConnectorError` subclass on any failure —
        never returns a partial or best-effort result silently.
        """
        ...
