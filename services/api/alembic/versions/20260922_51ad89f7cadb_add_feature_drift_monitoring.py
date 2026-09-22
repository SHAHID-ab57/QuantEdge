"""add feature drift monitoring

Revision ID: 51ad89f7cadb
Revises: b3d95f10c7e4
Create Date: 2026-09-22 12:00:00.000000

FEATURE-DRIFT-MONITOR: detect when a live prediction's input features are
extreme outliers relative to their training job's own stored normalization
(app.prediction.feature_drift), and auto-pause a live account's strategy
when its own fresh prediction comes back drifted.

- `predictions.feature_drift_status` / `feature_drift_worst_feature` /
  `feature_drift_worst_z`: every live prediction's own drift check,
  persisted alongside it. Existing rows default to 'unavailable' (never a
  guessed 'healthy' for a prediction this check never ran against).
- `paper_accounts.strategy_paused_reason` / `strategy_paused_at`: set only
  when the scheduler itself, not a human, disabled the strategy — today
  the only value is 'feature_drift'.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "51ad89f7cadb"
down_revision: str | None = "b3d95f10c7e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column(
            "feature_drift_status",
            sa.String(length=20),
            server_default="unavailable",
            nullable=False,
            comment="'healthy' | 'drifted' | 'unavailable' — this feature vector's own z-score check against the job's stored result_summary.normalization at prediction time (app.prediction.feature_drift.compute_feature_drift). 'unavailable' when the job carries no normalization stats to compare against, never a guessed 'healthy'.",
        ),
    )
    op.add_column(
        "predictions",
        sa.Column(
            "feature_drift_worst_feature",
            sa.String(length=100),
            nullable=True,
            comment="The single feature column with the largest-magnitude z-score this check found, or NULL when feature_drift_status is 'unavailable'.",
        ),
    )
    op.add_column(
        "predictions",
        sa.Column(
            "feature_drift_worst_z",
            sa.Float(),
            nullable=True,
            comment="That column's own signed z-score against the job's stored normalization.",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_paused_reason",
            sa.String(length=50),
            nullable=True,
            comment="Set only when PaperTradingStrategyScheduler itself flipped strategy_enabled to false (today: only 'feature_drift') — distinguishes an automated safety pause from a human's own PATCH .../strategy decision, which is otherwise indistinguishable from the outside. Cleared automatically the next time a human explicitly names `enabled` in a PATCH .../strategy request, whichever way they set it: an explicit human decision about this field always supersedes an automated one.",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_paused_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When strategy_paused_reason was set; NULL exactly when it is.",
        ),
    )
    op.create_check_constraint(
        op.f("ck_paper_accounts_strategy_paused_reason_valid"),
        "paper_accounts",
        "strategy_paused_reason IS NULL OR strategy_paused_reason IN ('feature_drift')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_paper_accounts_strategy_paused_reason_valid"), "paper_accounts", type_="check"
    )
    op.drop_column("paper_accounts", "strategy_paused_at")
    op.drop_column("paper_accounts", "strategy_paused_reason")
    op.drop_column("predictions", "feature_drift_worst_z")
    op.drop_column("predictions", "feature_drift_worst_feature")
    op.drop_column("predictions", "feature_drift_status")
