"""add paper trading margin, shorts, liquidation and funding

Revision ID: a7c41e9b3d52
Revises: d2d7b08d88e9
Create Date: 2026-09-20 15:10:00.000000

Isolated-margin short and leveraged positions for manually placed paper
orders (M3-E5-T2). Every new column has a server default that reproduces the
pre-existing long-only, unleveraged behaviour exactly, so existing rows keep
meaning what they always meant:

- `paper_positions`: `side='long'`, `leverage=1`, `margin` backfilled to the
  position's cost basis (`quantity * average_entry_price`), which is what an
  unleveraged long has always had locked up.
- `paper_accounts.peak_balance` was a *cash* high-water mark; the drawdown
  limit now measures *equity* (D3, an announced behaviour change), so it is
  raised to each account's current cost-basis equity where that is higher.
  It can only ever be raised, never lowered, by this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a7c41e9b3d52'
down_revision: str | None = 'd2d7b08d88e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- paper_accounts ---
    op.add_column('paper_accounts', sa.Column('max_leverage', sa.Numeric(precision=38, scale=18), server_default='5', nullable=False, comment='The highest leverage a manually-placed order on this account may use. The automated strategy is limited to 1x regardless of this value.'))
    op.add_column('paper_accounts', sa.Column('state_version', sa.Integer(), server_default='0', nullable=False, comment='Bumped by every guarded trade-effect update. The optimistic-concurrency guard matches on it, so it covers state (margin, positions, funding) that a balance comparison alone cannot see, e.g. a liquidation that forfeits margin without changing cash.'))
    op.create_check_constraint(op.f('ck_paper_accounts_max_leverage_valid'), 'paper_accounts', 'max_leverage >= 1 AND max_leverage <= 200')

    # --- paper_positions ---
    op.add_column('paper_positions', sa.Column('side', sa.String(length=5), server_default='long', nullable=False, comment="'long' | 'short'. Meaningful only while quantity > 0."))
    op.add_column('paper_positions', sa.Column('leverage', sa.Numeric(precision=38, scale=18), server_default='1', nullable=False, comment='Fixed when the position was opened; 1 for an unleveraged position.'))
    op.add_column('paper_positions', sa.Column('margin', sa.Numeric(precision=38, scale=18), server_default='0', nullable=False, comment='Isolated margin posted against this position (its whole notional at 1x).'))
    op.add_column('paper_positions', sa.Column('liquidation_price', sa.Numeric(precision=38, scale=18), nullable=True, comment='The mark price at which this position is liquidated; NULL if it cannot be.'))
    op.add_column('paper_positions', sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True, comment='When this position last went from flat to open — funding is only owed for funding times after it.'))
    op.execute("UPDATE paper_positions SET margin = quantity * average_entry_price, opened_at = created_at WHERE quantity > 0")
    op.create_check_constraint(op.f('ck_paper_positions_position_side_valid'), 'paper_positions', "side IN ('long', 'short')")
    op.create_check_constraint(op.f('ck_paper_positions_position_leverage_valid'), 'paper_positions', 'leverage >= 1')
    op.create_check_constraint(op.f('ck_paper_positions_margin_non_negative'), 'paper_positions', 'margin >= 0')

    # peak_balance: cash high-water mark -> equity high-water mark (D3). Raised only.
    op.execute(
        "UPDATE paper_accounts SET peak_balance = GREATEST(peak_balance, "
        "balance + COALESCE((SELECT SUM(margin) FROM paper_positions p "
        "WHERE p.account_id = paper_accounts.id AND p.quantity > 0), 0))"
    )

    # --- paper_orders ---
    op.add_column('paper_orders', sa.Column('position_side', sa.String(length=5), server_default='long', nullable=False, comment="'long' | 'short' — the kind of position this order opened, added to or reduced."))
    op.add_column('paper_orders', sa.Column('leverage', sa.Numeric(precision=38, scale=18), server_default='1', nullable=False, comment='The leverage of the position this order acted on.'))
    op.add_column('paper_orders', sa.Column('margin_applied', sa.Numeric(precision=38, scale=18), server_default='0', nullable=False, comment='Margin this order posted (opening/adding) or released (reducing/closing, before realized PnL); for a liquidation, the margin forfeited.'))
    op.add_column('paper_orders', sa.Column('reduce_only', sa.Boolean(), server_default='false', nullable=False, comment='The order was placed reduce-only: it could only shrink an existing position.'))
    op.add_column('paper_orders', sa.Column('gapped_through_bankruptcy', sa.Boolean(), server_default='false', nullable=False, comment='Liquidation only: the mark price had already passed the bankruptcy price, so the real loss would have exceeded the margin. The paper account\'s loss stays capped at the margin actually posted.'))
    op.add_column('paper_orders', sa.Column('trigger_price_basis', sa.String(length=15), nullable=True, comment="'mark' | 'last_fallback' for a liquidation: the price the trigger used. A liquidation is meant to run on the mark price; 'last_fallback' records that no mark price was available and the last traded price stood in."))
    op.drop_constraint(op.f('ck_paper_orders_trigger_reason_valid'), 'paper_orders', type_='check')
    op.create_check_constraint(op.f('ck_paper_orders_trigger_reason_valid'), 'paper_orders', "trigger_reason IS NULL OR trigger_reason IN ('stop_loss', 'take_profit', 'liquidation')")
    op.create_check_constraint(op.f('ck_paper_orders_position_side_valid'), 'paper_orders', "position_side IN ('long', 'short')")
    op.create_check_constraint(op.f('ck_paper_orders_trigger_price_basis_valid'), 'paper_orders', "trigger_price_basis IS NULL OR trigger_price_basis IN ('mark', 'last_fallback')")
    op.create_check_constraint(op.f('ck_paper_orders_order_leverage_valid'), 'paper_orders', 'leverage >= 1')

    # Column comments whose meaning changed (equity-based drawdown; short-aware thresholds).
    op.alter_column('paper_accounts', 'max_drawdown_pct', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=False, comment='If account equity falls below peak_balance * (1 - this / 100), trading_halted is set.', existing_comment='If balance falls below peak_balance * (1 - this / 100), trading_halted is set.')
    op.alter_column('paper_accounts', 'peak_balance', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=False, comment='The highest account EQUITY (cash + margin + unrealized PnL) ever reached — never decreases. The column keeps its original name for API compatibility; it was a cash high-water mark before the drawdown limit moved to equity.', existing_comment='The highest balance this account has ever reached — never decreases.')
    op.alter_column('paper_orders', 'trigger_reason', existing_type=sa.String(length=20), existing_nullable=True, comment="'stop_loss' | 'take_profit' | 'liquidation' for a market-triggered auto-close; NULL for a manually-placed order.", existing_comment="'stop_loss' | 'take_profit' for a market-triggered auto-close; NULL for a manually-placed order.")
    op.alter_column('paper_positions', 'stop_loss_price', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=True, comment="A long's stop-loss: closes at or below this price. A short's: at or above.", existing_comment='Auto-closes the position when the live price falls to or below this level.')
    op.alter_column('paper_positions', 'take_profit_price', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=True, comment="A long's take-profit: closes at or above this price. A short's: at or below.", existing_comment='Auto-closes the position when the live price rises to or above this level.')

    # --- funding_rates ---
    op.create_table('funding_rates',
    sa.Column('market_id', sa.Uuid(), nullable=False),
    sa.Column('funding_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('funding_rate', sa.Numeric(precision=38, scale=18), nullable=False, comment="Fraction per funding interval (0.0001 = 0.01%), converted from Delta's percent."),
    sa.Column('index_price', sa.Numeric(precision=38, scale=18), nullable=False, comment='The underlying index price at the funding time; the funding payment is position value at this price times the rate.'),
    sa.Column('mark_price', sa.Numeric(precision=38, scale=18), nullable=True),
    sa.Column('source', sa.String(length=50), server_default='delta_candles', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['market_id'], ['markets.id'], name=op.f('fk_funding_rates_market_id_markets'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_funding_rates')),
    sa.UniqueConstraint('market_id', 'funding_time', name='uq_funding_rates_time')
    )
    op.create_index(op.f('ix_funding_rates_market_id'), 'funding_rates', ['market_id'], unique=False)

    # --- paper_funding_settlements ---
    op.create_table('paper_funding_settlements',
    sa.Column('account_id', sa.Uuid(), nullable=False),
    sa.Column('symbol', sa.String(length=50), nullable=False),
    sa.Column('funding_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('position_side', sa.String(length=5), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=38, scale=18), nullable=False),
    sa.Column('index_price', sa.Numeric(precision=38, scale=18), nullable=False),
    sa.Column('funding_rate', sa.Numeric(precision=38, scale=18), nullable=False, comment='Fraction per interval (0.0001 = 0.01%).'),
    sa.Column('payment', sa.Numeric(precision=38, scale=18), nullable=False, comment='What the position paid; negative when it received funding.'),
    sa.Column('charged_to_margin', sa.Numeric(precision=38, scale=18), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("position_side IN ('long', 'short')", name=op.f('ck_paper_funding_settlements_funding_position_side_valid')),
    sa.ForeignKeyConstraint(['account_id'], ['paper_accounts.id'], name=op.f('fk_paper_funding_settlements_account_id_paper_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_paper_funding_settlements')),
    sa.UniqueConstraint('account_id', 'symbol', 'funding_time', name='uq_paper_funding_account_symbol_time')
    )
    op.create_index(op.f('ix_paper_funding_settlements_account_id'), 'paper_funding_settlements', ['account_id'], unique=False)
    op.create_index(op.f('ix_paper_funding_settlements_symbol'), 'paper_funding_settlements', ['symbol'], unique=False)


def downgrade() -> None:
    op.alter_column('paper_positions', 'take_profit_price', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=True, comment='Auto-closes the position when the live price rises to or above this level.', existing_comment="A long's take-profit: closes at or above this price. A short's: at or below.")
    op.alter_column('paper_positions', 'stop_loss_price', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=True, comment='Auto-closes the position when the live price falls to or below this level.', existing_comment="A long's stop-loss: closes at or below this price. A short's: at or above.")
    op.alter_column('paper_orders', 'trigger_reason', existing_type=sa.String(length=20), existing_nullable=True, comment="'stop_loss' | 'take_profit' for a market-triggered auto-close; NULL for a manually-placed order.", existing_comment="'stop_loss' | 'take_profit' | 'liquidation' for a market-triggered auto-close; NULL for a manually-placed order.")
    op.alter_column('paper_accounts', 'peak_balance', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=False, comment='The highest balance this account has ever reached — never decreases.', existing_comment='The highest account EQUITY (cash + margin + unrealized PnL) ever reached — never decreases. The column keeps its original name for API compatibility; it was a cash high-water mark before the drawdown limit moved to equity.')
    op.alter_column('paper_accounts', 'max_drawdown_pct', existing_type=sa.Numeric(precision=38, scale=18), existing_nullable=False, comment='If balance falls below peak_balance * (1 - this / 100), trading_halted is set.', existing_comment='If account equity falls below peak_balance * (1 - this / 100), trading_halted is set.')

    op.drop_index(op.f('ix_paper_funding_settlements_symbol'), table_name='paper_funding_settlements')
    op.drop_index(op.f('ix_paper_funding_settlements_account_id'), table_name='paper_funding_settlements')
    op.drop_table('paper_funding_settlements')
    op.drop_index(op.f('ix_funding_rates_market_id'), table_name='funding_rates')
    op.drop_table('funding_rates')

    op.drop_constraint(op.f('ck_paper_orders_order_leverage_valid'), 'paper_orders', type_='check')
    op.drop_constraint(op.f('ck_paper_orders_trigger_price_basis_valid'), 'paper_orders', type_='check')
    op.drop_constraint(op.f('ck_paper_orders_position_side_valid'), 'paper_orders', type_='check')
    op.drop_constraint(op.f('ck_paper_orders_trigger_reason_valid'), 'paper_orders', type_='check')
    op.create_check_constraint(op.f('ck_paper_orders_trigger_reason_valid'), 'paper_orders', "trigger_reason IS NULL OR trigger_reason IN ('stop_loss', 'take_profit')")
    op.drop_column('paper_orders', 'trigger_price_basis')
    op.drop_column('paper_orders', 'gapped_through_bankruptcy')
    op.drop_column('paper_orders', 'reduce_only')
    op.drop_column('paper_orders', 'margin_applied')
    op.drop_column('paper_orders', 'leverage')
    op.drop_column('paper_orders', 'position_side')

    op.drop_constraint(op.f('ck_paper_positions_margin_non_negative'), 'paper_positions', type_='check')
    op.drop_constraint(op.f('ck_paper_positions_position_leverage_valid'), 'paper_positions', type_='check')
    op.drop_constraint(op.f('ck_paper_positions_position_side_valid'), 'paper_positions', type_='check')
    op.drop_column('paper_positions', 'opened_at')
    op.drop_column('paper_positions', 'liquidation_price')
    op.drop_column('paper_positions', 'margin')
    op.drop_column('paper_positions', 'leverage')
    op.drop_column('paper_positions', 'side')

    op.drop_constraint(op.f('ck_paper_accounts_max_leverage_valid'), 'paper_accounts', type_='check')
    op.drop_column('paper_accounts', 'state_version')
    op.drop_column('paper_accounts', 'max_leverage')
