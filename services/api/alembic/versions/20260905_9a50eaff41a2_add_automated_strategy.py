"""add automated strategy

Revision ID: 9a50eaff41a2
Revises: 16e4c2531e7d
Create Date: 2026-09-05 15:59:45.125986

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9a50eaff41a2"
down_revision: str | None = "16e4c2531e7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also detected a one-word comment-only drift on
    # ml_dataset_builds.ml_dataset_id ("duplicated for lookup" vs
    # "duplicated here for lookup") — pre-existing, unrelated to this
    # migration's own change (see the identical note in 35fe2827d1fb,
    # 2f9216bd92c0, 7a3254fe72af, c1e00878df40, and 16e4c2531e7d, which
    # each found and skipped it in turn), so it's left out again here too.
    op.create_table(
        "paper_strategy_decisions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "training_job_id",
            sa.Uuid(),
            nullable=True,
            comment="The job this cycle requested a prediction from — the account's own "
            "strategy_training_job_id at the moment of this cycle.",
        ),
        sa.Column(
            "symbol",
            sa.String(length=50),
            nullable=True,
            comment="The job's own recorded symbol; NULL only if the job itself couldn't be "
            "resolved this cycle (see reason).",
        ),
        sa.Column(
            "action",
            sa.String(length=20),
            nullable=False,
            comment="'opened' | 'closed' | 'no_action' — what this cycle actually did.",
        ),
        sa.Column(
            "reason",
            sa.String(length=500),
            nullable=False,
            comment="Plain-language explanation, always present — including for 'no_action'.",
        ),
        sa.Column(
            "predicted_value",
            sa.JSON(),
            nullable=True,
            comment="The fresh prediction's own class label (or number, for a regressor); NULL "
            "if no prediction was obtained this cycle.",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=True,
            comment="The fresh prediction's own confidence (0-1); NULL if unavailable or no "
            "prediction was obtained.",
        ),
        sa.Column(
            "confidence_threshold_pct",
            sa.Numeric(precision=38, scale=18),
            nullable=False,
            comment="A snapshot of the account's own strategy_confidence_threshold_pct at the "
            "moment of this cycle — never re-read from the (possibly since-changed) account.",
        ),
        sa.Column("prediction_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('opened', 'closed', 'no_action')",
            name=op.f("ck_paper_strategy_decisions_paper_strategy_decision_action_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["paper_accounts.id"],
            name=op.f("fk_paper_strategy_decisions_account_id_paper_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["paper_orders.id"],
            name=op.f("fk_paper_strategy_decisions_order_id_paper_orders"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_id"],
            ["predictions.id"],
            name=op.f("fk_paper_strategy_decisions_prediction_id_predictions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["training_job_id"],
            ["training_jobs.id"],
            name=op.f("fk_paper_strategy_decisions_training_job_id_training_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_strategy_decisions")),
    )
    op.create_index(
        op.f("ix_paper_strategy_decisions_account_id"),
        "paper_strategy_decisions",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_paper_strategy_decisions_symbol"),
        "paper_strategy_decisions",
        ["symbol"],
        unique=False,
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="Opt-in automated strategy (app.services.paper_trading_strategy). Off by "
            "default — a researcher must explicitly enable it per account; there is no "
            "platform-wide default that turns it on.",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_training_job_id",
            sa.Uuid(),
            nullable=True,
            comment="The training job the strategy requests a fresh prediction from every "
            "cycle — its own recorded symbol/timeframe is what the strategy trades, never a "
            "separately-configured one. Required whenever strategy_enabled is true (enforced "
            "in PaperTradingService.update_strategy_config, not by a DB constraint, since it "
            "depends on two columns together).",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_confidence_threshold_pct",
            sa.Numeric(precision=38, scale=18),
            server_default="65",
            nullable=False,
            comment="A fresh prediction's own confidence (0-1 probability, reported here as a "
            "% for consistency with every other risk/threshold field on this row) must reach "
            "at least this before the strategy acts on it at all.",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_default_stop_loss_pct",
            sa.Numeric(precision=38, scale=18),
            server_default="5",
            nullable=False,
            comment="Every automated buy attaches a stop-loss this % below its own fill price "
            "— tunable per account, but never omittable: an automated position without one is "
            "not a configuration this feature can express.",
        ),
    )
    op.create_foreign_key(
        op.f("fk_paper_accounts_strategy_training_job_id_training_jobs"),
        "paper_accounts",
        "training_jobs",
        ["strategy_training_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_paper_accounts_strategy_confidence_threshold_pct_valid"),
        "paper_accounts",
        "strategy_confidence_threshold_pct > 0 AND strategy_confidence_threshold_pct <= 100",
    )
    op.create_check_constraint(
        op.f("ck_paper_accounts_strategy_default_stop_loss_pct_valid"),
        "paper_accounts",
        "strategy_default_stop_loss_pct > 0 AND strategy_default_stop_loss_pct < 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_paper_accounts_strategy_default_stop_loss_pct_valid"),
        "paper_accounts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_paper_accounts_strategy_confidence_threshold_pct_valid"),
        "paper_accounts",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_paper_accounts_strategy_training_job_id_training_jobs"),
        "paper_accounts",
        type_="foreignkey",
    )
    op.drop_column("paper_accounts", "strategy_default_stop_loss_pct")
    op.drop_column("paper_accounts", "strategy_confidence_threshold_pct")
    op.drop_column("paper_accounts", "strategy_training_job_id")
    op.drop_column("paper_accounts", "strategy_enabled")
    op.drop_index(op.f("ix_paper_strategy_decisions_symbol"), table_name="paper_strategy_decisions")
    op.drop_index(
        op.f("ix_paper_strategy_decisions_account_id"), table_name="paper_strategy_decisions"
    )
    op.drop_table("paper_strategy_decisions")
