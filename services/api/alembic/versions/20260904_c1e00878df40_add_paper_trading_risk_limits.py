"""add paper trading risk limits

Revision ID: c1e00878df40
Revises: 7a3254fe72af
Create Date: 2026-09-04 21:10:38.725540

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1e00878df40"
down_revision: str | None = "7a3254fe72af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also detected a one-word comment-only drift on
    # ml_dataset_builds.ml_dataset_id ("duplicated for lookup" vs
    # "duplicated here for lookup") — pre-existing, unrelated to this
    # migration's own change (see the identical note in 35fe2827d1fb,
    # 2f9216bd92c0, and 7a3254fe72af, which each found and skipped it in
    # turn), so it's left out again here too.
    op.add_column(
        "paper_accounts",
        sa.Column(
            "max_position_size_pct",
            sa.Numeric(precision=38, scale=18),
            nullable=False,
            server_default="10",
            comment="A single order's resulting position value may never exceed this "
            "percentage of current balance.",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "max_exposure_pct",
            sa.Numeric(precision=38, scale=18),
            nullable=False,
            server_default="50",
            comment="Total open-position value (every symbol, at current prices) may never "
            "exceed this percentage of current balance.",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "max_drawdown_pct",
            sa.Numeric(precision=38, scale=18),
            nullable=False,
            server_default="20",
            comment="If balance falls below peak_balance * (1 - this / 100), trading_halted "
            "is set.",
        ),
    )
    op.add_column(
        "paper_accounts",
        sa.Column(
            "trading_halted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Set once balance breaches the drawdown limit; does not clear itself on "
            "balance recovery — only an explicit resume-trading action clears it.",
        ),
    )
    # peak_balance has no single fixed default that's correct for every
    # existing row — it must start at least at that row's own current
    # balance — so it's added nullable, backfilled from the real data,
    # then locked to NOT NULL, rather than given a server_default.
    op.add_column(
        "paper_accounts",
        sa.Column(
            "peak_balance",
            sa.Numeric(precision=38, scale=18),
            nullable=True,
            comment="The highest balance this account has ever reached — never decreases.",
        ),
    )
    op.execute("UPDATE paper_accounts SET peak_balance = balance WHERE peak_balance IS NULL")
    op.alter_column("paper_accounts", "peak_balance", nullable=False)

    op.create_check_constraint(
        op.f("ck_paper_accounts_max_drawdown_pct_valid"),
        "paper_accounts",
        "max_drawdown_pct > 0 AND max_drawdown_pct <= 100",
    )
    op.create_check_constraint(
        op.f("ck_paper_accounts_max_exposure_pct_valid"),
        "paper_accounts",
        "max_exposure_pct > 0 AND max_exposure_pct <= 100",
    )
    op.create_check_constraint(
        op.f("ck_paper_accounts_max_position_size_pct_valid"),
        "paper_accounts",
        "max_position_size_pct > 0 AND max_position_size_pct <= 100",
    )
    op.create_check_constraint(
        op.f("ck_paper_accounts_peak_balance_non_negative"), "paper_accounts", "peak_balance >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_paper_accounts_peak_balance_non_negative"), "paper_accounts", type_="check"
    )
    op.drop_constraint(
        op.f("ck_paper_accounts_max_position_size_pct_valid"), "paper_accounts", type_="check"
    )
    op.drop_constraint(
        op.f("ck_paper_accounts_max_exposure_pct_valid"), "paper_accounts", type_="check"
    )
    op.drop_constraint(
        op.f("ck_paper_accounts_max_drawdown_pct_valid"), "paper_accounts", type_="check"
    )
    op.drop_column("paper_accounts", "peak_balance")
    op.drop_column("paper_accounts", "trading_halted")
    op.drop_column("paper_accounts", "max_drawdown_pct")
    op.drop_column("paper_accounts", "max_exposure_pct")
    op.drop_column("paper_accounts", "max_position_size_pct")
