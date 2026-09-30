"""add reddit comments table

Revision ID: 433b86f94f10
Revises: 75d437dff776
Create Date: 2026-09-27 18:34:35.010668

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "433b86f94f10"
down_revision: str | None = "75d437dff776"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also detected four unrelated pre-existing drifts (two
    # comment-wording drifts already known from prior migrations'
    # own notes, plus a paper_accounts.max_leverage comment drift and the
    # paper_strategy_decisions check-constraint name truncation) — left
    # out again here; not this migration's concern to fix.
    op.create_table(
        "reddit_comments",
        sa.Column(
            "reddit_id",
            sa.String(length=20),
            nullable=False,
            comment="Reddit's own comment id — the real idempotency key, checked before "
            "every insert.",
        ),
        sa.Column(
            "subreddit",
            sa.String(length=100),
            nullable=False,
            comment="Which configured subreddit this came from.",
        ),
        sa.Column(
            "author",
            sa.String(length=100),
            nullable=True,
            comment="The commenting user's name, when not deleted.",
        ),
        sa.Column(
            "body",
            sa.String(length=10000),
            nullable=False,
            comment="The comment's raw text — '[deleted]'/'[removed]' for a comment whose "
            "body is no longer available (still counted toward volume, excluded from "
            "sentiment).",
        ),
        sa.Column(
            "score",
            sa.Integer(),
            nullable=False,
            comment="The comment's own score/upvotes at time of ingestion.",
        ),
        sa.Column(
            "sentiment_score",
            sa.Float(),
            nullable=True,
            comment="VADER compound sentiment in [-1, 1] (app.connectors.reddit"
            ".score_comment). Null for a deleted/removed/empty body, which has no real "
            "sentiment to score.",
        ),
        sa.Column(
            "created_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When Reddit reports the comment was created — never the ingestion "
            "time (see ingested_at).",
        ),
        sa.Column(
            "permalink",
            sa.String(length=500),
            nullable=True,
            comment="Always null today — 'permalink' is not a valid Arctic Shift "
            "`fields=` name, confirmed live (app.connectors.reddit's own module "
            "docstring). Column kept for a future fix rather than removed outright.",
        ),
        sa.Column(
            "raw_payload",
            sa.JSON(),
            nullable=False,
            comment="Arctic Shift's own untouched comment record, kept for audit — never "
            "re-parsed by anything downstream.",
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this platform actually stored the row — distinct from "
            "created_utc, which is when Reddit reports the comment went live.",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reddit_comments")),
    )
    op.create_index(
        op.f("ix_reddit_comments_created_utc"), "reddit_comments", ["created_utc"], unique=False
    )
    op.create_index(
        op.f("ix_reddit_comments_reddit_id"), "reddit_comments", ["reddit_id"], unique=True
    )
    op.create_index(
        op.f("ix_reddit_comments_subreddit"), "reddit_comments", ["subreddit"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reddit_comments_subreddit"), table_name="reddit_comments")
    op.drop_index(op.f("ix_reddit_comments_reddit_id"), table_name="reddit_comments")
    op.drop_index(op.f("ix_reddit_comments_created_utc"), table_name="reddit_comments")
    op.drop_table("reddit_comments")
