"""add order flow capture tables

Revision ID: 252f1e39f532
Revises: 01c81f537e54
Create Date: 2026-09-11 01:30:52.470646

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "252f1e39f532"
down_revision: str | None = "01c81f537e54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also re-detected the same two pre-existing drifts every
    # migration since 35fe2827d1fb has found and skipped — a comment-only
    # wording drift on ml_dataset_builds.ml_dataset_id and a cosmetic
    # check-constraint name truncation on paper_strategy_decisions. Left out
    # again here; not this migration's concern (see 156feb63e12d's note).
    op.create_table(
        "orderbook_snapshots",
        sa.Column("exchange", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="The reconstructed book's own latest exchange event_time; falls back "
            "to the capture instant when the book carries none.",
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this platform actually wrote the row.",
        ),
        sa.Column(
            "sequence",
            sa.Integer(),
            nullable=True,
            comment="The book's last-applied exchange sequence number, when the feed provides one.",
        ),
        sa.Column(
            "depth",
            sa.Integer(),
            nullable=False,
            comment="Levels per side actually stored in this row.",
        ),
        sa.Column(
            "bids",
            sa.JSON(),
            nullable=False,
            comment='Descending [["price","size"], ...] pairs.',
        ),
        sa.Column(
            "asks",
            sa.JSON(),
            nullable=False,
            comment='Ascending [["price","size"], ...] pairs.',
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orderbook_snapshots")),
    )
    op.create_index(
        op.f("ix_orderbook_snapshots_symbol"), "orderbook_snapshots", ["symbol"], unique=False
    )
    op.create_index(
        "ix_orderbook_snapshots_symbol_event_time",
        "orderbook_snapshots",
        ["symbol", "event_time"],
        unique=False,
    )
    op.create_table(
        "trade_flow",
        sa.Column("exchange", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Exchange-assigned event time.",
        ),
        sa.Column(
            "trade_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="The fill's own timestamp when distinct from event_time.",
        ),
        sa.Column(
            "side",
            sa.String(length=8),
            nullable=False,
            comment="Aggressor side as normalized upstream: buy / sell / bid / ask / unknown.",
        ),
        sa.Column("price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("size", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_flow")),
    )
    op.create_index(op.f("ix_trade_flow_symbol"), "trade_flow", ["symbol"], unique=False)
    op.create_index(
        "ix_trade_flow_symbol_event_time",
        "trade_flow",
        ["symbol", "event_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_flow_symbol_event_time", table_name="trade_flow")
    op.drop_index(op.f("ix_trade_flow_symbol"), table_name="trade_flow")
    op.drop_table("trade_flow")
    op.drop_index("ix_orderbook_snapshots_symbol_event_time", table_name="orderbook_snapshots")
    op.drop_index(op.f("ix_orderbook_snapshots_symbol"), table_name="orderbook_snapshots")
    op.drop_table("orderbook_snapshots")
