"""add training job dataset limit

Revision ID: 57b6bdcad9da
Revises: 51ad89f7cadb
Create Date: 2026-09-23 09:00:00.000000

RETRAIN-WITH-MINIMUM-WINDOW: `TrainingJobCreateRequest.limit` (new) needs
somewhere to persist. Without it, a job with an explicit `dataset_start`/
`dataset_end` wider than `candles_default_limit` (100) silently trained on
only the first 100 candles (ascending) within that range -- no error, no
warning -- which is exactly the too-narrow-training-window trap
FEATURE-DRIFT-MONITOR exists to catch. See
`docs/research/RETRAIN_WINDOW_ANALYSIS.md`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "57b6bdcad9da"
down_revision: str | None = "51ad89f7cadb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_jobs",
        sa.Column(
            "dataset_limit",
            sa.Integer(),
            nullable=True,
            comment="Explicit candle-row ceiling for this job's own dataset build; NULL means the load_dataset stage's own default (candles_default_limit, currently 100). Set this whenever dataset_start/dataset_end span more real candles than the default would return -- omitting it silently truncates a wide date range to the first candles_default_limit candles (ascending) within it, not an error, which is exactly the too-narrow-window trap FEATURE-DRIFT-MONITOR exists to catch (see docs/research/RETRAIN_WINDOW_ANALYSIS.md).",
        ),
    )


def downgrade() -> None:
    op.drop_column("training_jobs", "dataset_limit")
