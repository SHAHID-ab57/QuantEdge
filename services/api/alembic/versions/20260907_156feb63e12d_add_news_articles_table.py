"""add news articles table

Revision ID: 156feb63e12d
Revises: fadfaba274eb
Create Date: 2026-09-07 00:29:34.637017

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "156feb63e12d"
down_revision: str | None = "fadfaba274eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also detected the same two pre-existing drifts every
    # migration since 35fe2827d1fb has found and skipped — see
    # fadfaba274eb's own identical note for the full account (a
    # comment-only wording drift on ml_dataset_builds.ml_dataset_id, and a
    # cosmetic check-constraint name truncation on
    # paper_strategy_decisions). Left out again here; not this
    # migration's concern to fix.
    op.create_table(
        "news_articles",
        sa.Column(
            "marketaux_uuid",
            sa.String(length=64),
            nullable=False,
            comment="Marketaux's own stable article identifier — the real idempotency "
            "key, checked before every insert.",
        ),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column(
            "snippet",
            sa.String(length=1000),
            nullable=True,
            comment="A short excerpt of the article body, when Marketaux provides one.",
        ),
        sa.Column(
            "source",
            sa.String(length=255),
            nullable=False,
            comment="The domain that published the article.",
        ),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When Marketaux reports the article was published — never the "
            "ingestion time (see ingested_at).",
        ),
        sa.Column(
            "sentiment_score",
            sa.Float(),
            nullable=True,
            comment="Mean sentiment_score across this article's own tracked-symbol "
            "entities (never diluted by unrelated entities — this connector always "
            "queries with filter_entities=true). Null when no tracked entity carried "
            "a score.",
        ),
        sa.Column(
            "primary_symbol",
            sa.String(length=50),
            nullable=True,
            comment="The first tracked symbol this article matched — a plain, indexed, "
            "cross-backend-portable column for the article-listing API's own symbol "
            "filter. `symbols` (below) is the complete list; this is the same value's "
            "own first entry, kept separately rather than queried out of a JSON "
            "column SQLite and Postgres wouldn't filter identically.",
        ),
        sa.Column(
            "symbols",
            sa.JSON(),
            nullable=False,
            comment="The tracked symbol(s) actually matched on this article (e.g. "
            '["ETHUSD"]) — a subset of the connector\'s own configured '
            "marketaux_symbols, never the full unrelated-entity list Marketaux would "
            "return without filter_entities=true.",
        ),
        sa.Column(
            "raw_payload",
            sa.JSON(),
            nullable=False,
            comment="Marketaux's own untouched article record, kept for audit — never "
            "re-parsed by anything downstream.",
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this platform actually stored the row — distinct from "
            "published_at, which is when Marketaux reports the article went live.",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_articles")),
    )
    op.create_index(
        op.f("ix_news_articles_marketaux_uuid"), "news_articles", ["marketaux_uuid"], unique=True
    )
    op.create_index(
        op.f("ix_news_articles_primary_symbol"), "news_articles", ["primary_symbol"], unique=False
    )
    op.create_index(
        op.f("ix_news_articles_published_at"), "news_articles", ["published_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_news_articles_published_at"), table_name="news_articles")
    op.drop_index(op.f("ix_news_articles_primary_symbol"), table_name="news_articles")
    op.drop_index(op.f("ix_news_articles_marketaux_uuid"), table_name="news_articles")
    op.drop_table("news_articles")
