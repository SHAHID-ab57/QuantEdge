"""add strategy volatility training job

Revision ID: 75d437dff776
Revises: 57b6bdcad9da
Create Date: 2026-09-24 22:35:16.830045

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "75d437dff776"
down_revision: str | None = "57b6bdcad9da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also detected unrelated comment-text/quote-style drift on
    # ml_dataset_builds.ml_dataset_id, paper_accounts.max_leverage, and
    # training_jobs.dataset_limit, plus a check-constraint name-truncation
    # churn on paper_strategy_decisions (Postgres's own identifier-length
    # truncation of the constraint name, not a real definition change) —
    # all pre-existing, unrelated to this migration's own change, so left
    # out here too (see the identical note in 9a50eaff41a2 and every
    # migration since for the ml_dataset_builds case).
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_volatility_training_job_id",
            sa.Uuid(),
            nullable=True,
            comment="VOLATILITY-STOP-WIDTH (Option B): the logistic_regression job whose "
            "fresh volatility_regime forecast scales a new automated entry's stop-loss width "
            "— wider ahead of a forecast 'expand', tighter ahead of 'contract'. Optional; "
            "NULL means every automated entry uses strategy_default_stop_loss_pct unscaled, "
            "the same as before this feature existed. Never validated at write time beyond "
            "the FK itself — a job that is later deleted, retrained to a different "
            "model_type, or never trained on the symbol being traded is a runtime "
            "fail-closed case (PaperTradingStrategyScheduler falls back to "
            "strategy_default_stop_loss_pct), not a rejected configuration, mirroring how a "
            "drifted forecast is handled the same way rather than raising.",
        ),
    )
    op.create_foreign_key(
        op.f("fk_paper_accounts_strategy_volatility_training_job_id_training_jobs"),
        "paper_accounts",
        "training_jobs",
        ["strategy_volatility_training_job_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_paper_accounts_strategy_volatility_training_job_id_training_jobs"),
        "paper_accounts",
        type_="foreignkey",
    )
    op.drop_column("paper_accounts", "strategy_volatility_training_job_id")
