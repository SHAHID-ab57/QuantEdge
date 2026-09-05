"""add stop loss take profit

Revision ID: 16e4c2531e7d
Revises: c1e00878df40
Create Date: 2026-09-05 14:54:09.543824

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "16e4c2531e7d"
down_revision: str | None = "c1e00878df40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also detected a one-word comment-only drift on
    # ml_dataset_builds.ml_dataset_id ("duplicated for lookup" vs
    # "duplicated here for lookup") — pre-existing, unrelated to this
    # migration's own change (see the identical note in 35fe2827d1fb,
    # 2f9216bd92c0, 7a3254fe72af, and c1e00878df40, which each found and
    # skipped it in turn), so it's left out again here too.
    op.add_column(
        "paper_orders",
        sa.Column(
            "trigger_reason",
            sa.String(length=20),
            nullable=True,
            comment="'stop_loss' | 'take_profit' for a market-triggered auto-close; NULL for a "
            "manually-placed order.",
        ),
    )
    op.create_check_constraint(
        op.f("ck_paper_orders_trigger_reason_valid"),
        "paper_orders",
        "trigger_reason IS NULL OR trigger_reason IN ('stop_loss', 'take_profit')",
    )
    op.add_column(
        "paper_positions",
        sa.Column(
            "stop_loss_price",
            sa.Numeric(precision=38, scale=18),
            nullable=True,
            comment="Auto-closes the position when the live price falls to or below this level.",
        ),
    )
    op.add_column(
        "paper_positions",
        sa.Column(
            "take_profit_price",
            sa.Numeric(precision=38, scale=18),
            nullable=True,
            comment="Auto-closes the position when the live price rises to or above this level.",
        ),
    )
    op.create_check_constraint(
        op.f("ck_paper_positions_stop_loss_price_non_negative"),
        "paper_positions",
        "stop_loss_price IS NULL OR stop_loss_price >= 0",
    )
    op.create_check_constraint(
        op.f("ck_paper_positions_take_profit_price_non_negative"),
        "paper_positions",
        "take_profit_price IS NULL OR take_profit_price >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_paper_positions_take_profit_price_non_negative"),
        "paper_positions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_paper_positions_stop_loss_price_non_negative"), "paper_positions", type_="check"
    )
    op.drop_column("paper_positions", "take_profit_price")
    op.drop_column("paper_positions", "stop_loss_price")
    op.drop_constraint(op.f("ck_paper_orders_trigger_reason_valid"), "paper_orders", type_="check")
    op.drop_column("paper_orders", "trigger_reason")
