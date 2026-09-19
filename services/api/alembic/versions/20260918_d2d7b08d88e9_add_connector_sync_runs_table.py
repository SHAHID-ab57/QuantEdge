"""add connector sync runs table

Revision ID: d2d7b08d88e9
Revises: 881f70c8d442
Create Date: 2026-09-18 22:31:30.100856

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd2d7b08d88e9'
down_revision: str | None = '881f70c8d442'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Scoped to this task alone — autogenerate also picked up two
    # unrelated, pre-existing drift items (a comment-text fix on
    # ml_dataset_builds.ml_dataset_id, a check-constraint rename on
    # paper_strategy_decisions) that predate this change and are not part
    # of it; left out of this migration deliberately, not lost.
    op.create_table('connector_sync_runs',
    sa.Column('source', sa.String(length=50), nullable=False, comment="The registered connector's own source identifier — same value as external_data_points.source."),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, comment='When this sync attempt began (wall-clock, not perf_counter).'),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False, comment='When this sync attempt finished, success or failure.'),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('received', sa.Integer(), nullable=False),
    sa.Column('inserted', sa.Integer(), nullable=False),
    sa.Column('updated', sa.Integer(), nullable=False),
    sa.Column('duplicates_skipped', sa.Integer(), nullable=False),
    sa.Column('rejected', sa.Integer(), nullable=False),
    sa.Column('duration_seconds', sa.Float(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True, comment="Set only when success is False — the exception's own str(), for a human debugging a connector that has started failing every tick."),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_connector_sync_runs'))
    )
    op.create_index(op.f('ix_connector_sync_runs_source'), 'connector_sync_runs', ['source'], unique=False)
    op.create_index(op.f('ix_connector_sync_runs_started_at'), 'connector_sync_runs', ['started_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_connector_sync_runs_started_at'), table_name='connector_sync_runs')
    op.drop_index(op.f('ix_connector_sync_runs_source'), table_name='connector_sync_runs')
    op.drop_table('connector_sync_runs')