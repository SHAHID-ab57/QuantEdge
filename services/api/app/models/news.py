"""News article storage — a dedicated table for Marketaux, not a bolt-on
to `external_data_points`.

`ExternalDataPoint` is deliberately narrow: one connector, one numeric
`value` per timestamp. A real news article has genuinely richer shape —
headline, source, a link, per-entity sentiment — that doesn't fit that
table without either losing detail or adding article-specific columns
five other connectors already share cleanly. This table holds that detail
in full; the daily aggregate sentiment the ML pipeline actually consumes
is computed from these rows and mirrored into `external_data_points`
under its own source (`news_sentiment`, see
`app.connectors.marketaux.MARKETAUX_SOURCE`) — everything downstream of
that mirror uses the exact same feature-lookup pattern as every other
connector, with no news-specific branch anywhere in it.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel

__all__ = ["NewsArticle"]


class NewsArticle(BaseModel):
    """One real news article ingested from a registered news connector.

    `marketaux_uuid` — not `id` — is the real idempotency key: Marketaux's
    own stable identifier for this exact article, unique regardless of how
    many times it's re-fetched across overlapping sync windows (mirroring
    why `ExternalDataPoint` needs a `(source, symbol, timestamp)` uniqueness
    check at all, but simpler here since a genuinely unique source-provided
    id already exists — no timestamp-based dedup heuristic needed).
    """

    __tablename__ = "news_articles"

    marketaux_uuid: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="Marketaux's own stable article identifier — the real idempotency key, "
        "checked before every insert.",
    )
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    snippet: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="A short excerpt of the article body, when Marketaux provides one.",
    )
    source: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="The domain that published the article."
    )
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When Marketaux reports the article was published — never the ingestion "
        "time (see ingested_at).",
    )
    sentiment_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Mean sentiment_score across this article's own tracked-symbol entities "
        "(never diluted by unrelated entities — this connector always queries with "
        "filter_entities=true). Null when no tracked entity carried a score.",
    )
    primary_symbol: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="The first tracked symbol this article matched — a plain, indexed, "
        "cross-backend-portable column for the article-listing API's own symbol "
        "filter. `symbols` (below) is the complete list; this is the same value's "
        "own first entry, kept separately rather than queried out of a JSON column "
        "SQLite and Postgres wouldn't filter identically.",
    )
    symbols: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        comment="The tracked symbol(s) actually matched on this article (e.g. "
        '["ETHUSD"]) — a subset of the connector\'s own configured '
        "marketaux_symbols, never the full unrelated-entity list Marketaux "
        "would return without filter_entities=true.",
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Marketaux's own untouched article record, kept for audit — never "
        "re-parsed by anything downstream.",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this platform actually stored the row — distinct from "
        "published_at, which is when Marketaux reports the article went live.",
    )
