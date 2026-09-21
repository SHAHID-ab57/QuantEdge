"""add strategy leverage and decision direction

Revision ID: b3d95f10c7e4
Revises: a7c41e9b3d52
Create Date: 2026-09-21 10:00:00.000000

M3-E5-T3: the automated strategy trades long and short at one fixed,
per-account leverage.

- `paper_accounts.strategy_leverage` (default 2). **Behaviour change for an
  account whose strategy is already enabled:** on its next tick it will trade at
  2x and may open shorts, where before it opened only unleveraged longs.
- `paper_strategy_decisions.direction` / `strategy_leverage`: every cycle now
  records the side it concerned and the leverage in force. Rows from before are
  NULL direction and 1x, which is what they were.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3d95f10c7e4"
down_revision: str | None = "a7c41e9b3d52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_accounts",
        sa.Column(
            "strategy_leverage",
            sa.Numeric(precision=38, scale=18),
            server_default="2",
            nullable=False,
            comment="The ONE leverage every automated entry uses, long or short. A fixed, per-account setting: it is never read from, scaled by, or derived from a prediction's confidence (which has been measured to carry no reliable relationship to being right). Must not exceed max_leverage.",
        ),
    )
    op.create_check_constraint(
        op.f("ck_paper_accounts_strategy_leverage_valid"),
        "paper_accounts",
        "strategy_leverage >= 1 AND strategy_leverage <= 200",
    )
    op.alter_column(
        "paper_accounts",
        "strategy_default_stop_loss_pct",
        existing_type=sa.Numeric(precision=38, scale=18),
        existing_nullable=False,
        existing_server_default="5",
        comment="Every automated entry attaches a stop-loss this % on the losing side of its own fill price (below a long's, above a short's) — tunable per account, but never omittable: an automated position without one is not a configuration this feature can express.",
        existing_comment="Every automated buy attaches a stop-loss this % below its own fill price — tunable per account, but never omittable: an automated position without one is not a configuration this feature can express.",
    )
    op.alter_column(
        "paper_accounts",
        "max_leverage",
        existing_type=sa.Numeric(precision=38, scale=18),
        existing_nullable=False,
        existing_server_default="5",
        comment="The highest leverage any order on this account may use, manual or automated: the ceiling on a manual order's leverage and on the automated strategy's fixed strategy_leverage.",
        existing_comment="The highest leverage a manually-placed order on this account may use. The automated strategy is limited to 1x regardless of this value.",
    )
    op.add_column(
        "paper_strategy_decisions",
        sa.Column(
            "direction",
            sa.String(length=5),
            nullable=True,
            comment="'long' | 'short' — the side this cycle concerned: the position it opened or closed, or, for a no_action cycle, the side the model's call pointed at (up = long, down = short). NULL only when there was no directional call at all.",
        ),
    )
    op.add_column(
        "paper_strategy_decisions",
        sa.Column(
            "strategy_leverage",
            sa.Numeric(precision=38, scale=18),
            server_default="1",
            nullable=False,
            comment="A snapshot of the account's own strategy_leverage at the moment of this cycle (rows from before leverage existed were 1x), never re-read from the possibly-since-changed account.",
        ),
    )
    op.create_check_constraint(
        op.f("ck_paper_strategy_decisions_decision_direction_valid"),
        "paper_strategy_decisions",
        "direction IS NULL OR direction IN ('long', 'short')",
    )


def downgrade() -> None:
    op.alter_column(
        "paper_accounts",
        "max_leverage",
        existing_type=sa.Numeric(precision=38, scale=18),
        existing_nullable=False,
        existing_server_default="5",
        comment="The highest leverage a manually-placed order on this account may use. The automated strategy is limited to 1x regardless of this value.",
        existing_comment="The highest leverage any order on this account may use, manual or automated: the ceiling on a manual order's leverage and on the automated strategy's fixed strategy_leverage.",
    )
    op.drop_constraint(
        op.f("ck_paper_strategy_decisions_decision_direction_valid"),
        "paper_strategy_decisions",
        type_="check",
    )
    op.drop_column("paper_strategy_decisions", "strategy_leverage")
    op.drop_column("paper_strategy_decisions", "direction")
    op.alter_column(
        "paper_accounts",
        "strategy_default_stop_loss_pct",
        existing_type=sa.Numeric(precision=38, scale=18),
        existing_nullable=False,
        existing_server_default="5",
        comment="Every automated buy attaches a stop-loss this % below its own fill price — tunable per account, but never omittable: an automated position without one is not a configuration this feature can express.",
        existing_comment="Every automated entry attaches a stop-loss this % on the losing side of its own fill price (below a long's, above a short's) — tunable per account, but never omittable: an automated position without one is not a configuration this feature can express.",
    )
    op.drop_constraint(
        op.f("ck_paper_accounts_strategy_leverage_valid"), "paper_accounts", type_="check"
    )
    op.drop_column("paper_accounts", "strategy_leverage")
