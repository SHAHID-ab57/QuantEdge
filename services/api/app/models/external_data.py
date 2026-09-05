"""External data point storage — one generic table every connector shares.

Built for the Fear & Greed connector and every connector after it, not
one table per source (see `app/connectors/` for the ingestion side, and
`ARCHITECTURE.md` § "External Data Connectors" for the full design). A
per-source table would mean a new migration, a new repository, and a new
feature-context wiring path for every future connector — this table
means adding one is only ever a new connector module plus a new feature
generator.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel

__all__ = ["ExternalDataPoint"]


class ExternalDataPoint(BaseModel):
    """One external data point from a registered connector.

    Deliberately **not** `TimestampMixin`: there is no "update" semantic
    here (a point is fetched once and never mutated — re-running ingestion
    for an already-stored `timestamp` is a no-op, not an update, see
    `app.services.external_data_ingest`), so an `updated_at` column would
    be permanently equal to `ingested_at` and mean nothing. `ingested_at`
    is its own column, distinct from `timestamp`, because the two answer
    genuinely different questions: `timestamp` is when the *source*
    reported the value; `ingested_at` is when *this platform* actually
    stored the row — a gap between them (a backfill run today for data
    from years ago) is expected and informative, not a bug.
    """

    __tablename__ = "external_data_points"

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="The registered connector's own source identifier, e.g. 'fear_greed' "
        "(app.connectors.registry.ConnectorMetadata.source).",
    )
    symbol: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Market this point applies to; NULL for a source-wide/global value — "
        "Fear & Greed has no per-symbol variant.",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When this value was observed/reported by the source itself — never "
        "the ingestion time (see ingested_at).",
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="The connector's own raw record for this point, kept for audit — "
        "never re-parsed by anything downstream.",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this platform actually stored the row — distinct from "
        "timestamp, which is when the source itself reported the value.",
    )

    __table_args__ = (
        # A defensive backstop, not the sole idempotency guarantee: Postgres
        # (and SQLite) both treat two NULL `symbol`s as distinct for
        # uniqueness purposes, so a source-wide connector like Fear & Greed
        # cannot rely on this constraint alone to reject a duplicate
        # re-ingestion of the same `timestamp` — see
        # `app.repositories.external_data.ExternalDataRepository
        # .list_existing_timestamps`, which is the real, backend-portable
        # idempotency check `app.services.external_data_ingest` uses before
        # this constraint is ever reached.
        UniqueConstraint(
            "source", "symbol", "timestamp", name="uq_external_data_points_source_symbol_timestamp"
        ),
    )
