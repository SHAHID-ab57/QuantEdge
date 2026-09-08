"""add dataset_start and dataset_end to training_jobs

Revision ID: 01c81f537e54
Revises: 156feb63e12d
Create Date: 2026-09-08 23:09:19.680092

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "01c81f537e54"
down_revision: str | None = "156feb63e12d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_jobs",
        sa.Column(
            "dataset_start",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "Explicit candle-range start this job trains on; NULL means the "
                "load_dataset stage's own default (the most recent candles for "
                "symbol/timeframe, never the oldest — see app/services/candle_points.py)."
            ),
        ),
    )
    op.add_column(
        "training_jobs",
        sa.Column(
            "dataset_end",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Explicit candle-range end this job trains on; must be set together with dataset_start.",
        ),
    )


def downgrade() -> None:
    op.drop_column("training_jobs", "dataset_end")
    op.drop_column("training_jobs", "dataset_start")
