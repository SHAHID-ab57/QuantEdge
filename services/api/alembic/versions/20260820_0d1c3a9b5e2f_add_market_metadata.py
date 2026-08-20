"""add market metadata columns

Revision ID: 0d1c3a9b5e2f
Revises: 1402faec05f9
Create Date: 2026-08-20 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0d1c3a9b5e2f"
down_revision: str | None = "1402faec05f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column("delta_product_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("delta_contract_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("tick_size", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("funding_method", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("funding_interval_seconds", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("listing_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_markets_delta_product_id"),
        "markets",
        ["delta_product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_markets_delta_product_id"), table_name="markets")
    op.drop_column("markets", "listing_date")
    op.drop_column("markets", "funding_interval_seconds")
    op.drop_column("markets", "funding_method")
    op.drop_column("markets", "tick_size")
    op.drop_column("markets", "delta_contract_type")
    op.drop_column("markets", "delta_product_id")