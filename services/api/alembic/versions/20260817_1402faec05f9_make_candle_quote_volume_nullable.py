"""make candle quote volume nullable

Delta Exchange candles do not include a quote volume field, so the column
must accept NULL instead of forcing a fabricated value.

Revision ID: 1402faec05f9
Revises: 592cf2283d14
Create Date: 2026-08-17 12:08:30.780664

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1402faec05f9"
down_revision: str | None = "592cf2283d14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "candles",
        "quote_volume",
        existing_type=sa.Numeric(precision=38, scale=18),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "candles",
        "quote_volume",
        existing_type=sa.Numeric(precision=38, scale=18),
        nullable=False,
    )
