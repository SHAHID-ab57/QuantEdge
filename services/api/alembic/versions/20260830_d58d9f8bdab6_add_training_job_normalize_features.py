"""add training job normalize_features

Revision ID: d58d9f8bdab6
Revises: 34ade0f119b6
Create Date: 2026-08-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d58d9f8bdab6"
down_revision: str | None = "34ade0f119b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_jobs",
        sa.Column(
            "normalize_features",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment=(
                "Whether to z-score normalize numeric feature columns (fit on the train "
                "split alone) before a requires_real_data adapter trains/predicts. "
                "Ignored by an adapter that declares requires_real_data=False."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("training_jobs", "normalize_features")
