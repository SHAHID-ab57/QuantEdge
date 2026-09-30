"""Reddit comment storage — a dedicated table for Arctic Shift, mirroring
`app.models.news.NewsArticle`'s own reasoning exactly.

`ExternalDataPoint` is deliberately narrow: one connector, one numeric
`value` per timestamp. A real comment has genuinely richer shape (body
text, author, subreddit, score) that doesn't fit that table without
losing detail. This table holds that detail in full; the two daily
aggregates the ML pipeline actually consumes (comment volume, mean VADER
sentiment) are computed from these rows and mirrored into
`external_data_points` under their own sources (`reddit_volume`,
`reddit_sentiment`, see `app.connectors.reddit`) — everything downstream
of that mirror uses the exact same feature-lookup pattern as every other
connector, with no Reddit-specific branch anywhere in it.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel

__all__ = ["RedditComment"]


class RedditComment(BaseModel):
    """One real Reddit comment ingested via Arctic Shift.

    `reddit_id` — not `id` — is the real idempotency key: Reddit's own
    comment id (globally unique, no `(source, symbol, timestamp)`-style
    compound check needed, mirroring `NewsArticle.marketaux_uuid`'s own
    reasoning exactly).
    """

    __tablename__ = "reddit_comments"

    reddit_id: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
        comment="Reddit's own comment id — the real idempotency key, checked before "
        "every insert.",
    )
    subreddit: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Which configured subreddit this came from.",
    )
    author: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="The commenting user's name, when not deleted."
    )
    body: Mapped[str] = mapped_column(
        String(10000),
        nullable=False,
        comment="The comment's raw text — '[deleted]'/'[removed]' for a comment whose "
        "body is no longer available (still counted toward volume, excluded from "
        "sentiment).",
    )
    score: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="The comment's own score/upvotes at time of ingestion."
    )
    sentiment_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="VADER compound sentiment in [-1, 1] (app.connectors.reddit.score_comment). "
        "Null for a deleted/removed/empty body, which has no real sentiment to score.",
    )
    created_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When Reddit reports the comment was created — never the ingestion time "
        "(see ingested_at).",
    )
    permalink: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Always null today — 'permalink' is not a valid Arctic Shift `fields=` "
        "name, confirmed live (app.connectors.reddit's own module docstring). Column "
        "kept for a future fix rather than removed outright.",
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Arctic Shift's own untouched comment record, kept for audit — never "
        "re-parsed by anything downstream.",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this platform actually stored the row — distinct from "
        "created_utc, which is when Reddit reports the comment went live.",
    )
