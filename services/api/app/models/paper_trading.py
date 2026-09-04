"""Paper Trading models — a virtual account, its filled orders, and its
materialized open positions.

Long-only, market-orders-only, no automation (per this feature's own
spec) — there is deliberately no `side="short"`, no leverage/margin
column anywhere here, and no scheduled/strategy-driven order path. Those
are separate, later milestones.

`PaperPosition` is **materialized**, not recomputed from `PaperOrder`
history on every read — the same "store the whole answer, never
re-derive it for every read" precedent `Prediction`/`EvaluationBenchmarkRun`
already established, just applied to a running position instead of a
finished record.

Every price this module ever touches is `Numeric(38, 18)`, matching
`Candle`'s own precision/scale — a paper fill is priced in the same real
market data as everything else on this platform, never a separate,
looser numeric type.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin

PRECISION = 38
SCALE = 18

ORDER_SIDES = ("buy", "sell")
PRICE_SOURCES = ("ticker", "trade", "candle_close")


class PaperAccount(BaseModel, TimestampMixin):
    """One virtual trading account: its cash balance and cumulative realized PnL.

    `balance` is cash only — buying converts cash into a position (tracked
    separately by `PaperPosition`, not blended into this row), and selling
    converts it back. `realized_pnl` accumulates the *actual* outcome of
    every order: a buy's own fee (an immediate, certain cost) and, for a
    sell, `(fill_price - average_entry_price) * quantity - fee` — see
    `app/services/paper_trading.py`'s own docstring for the full accounting
    model and why it reconciles exactly against `balance` once every
    position is flat. Unrealized PnL is never stored here — it depends on
    a live price lookup and is computed fresh on every read (`GET
    .../summary`).
    """

    __tablename__ = "paper_accounts"

    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    starting_balance: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    balance: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    realized_pnl: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("starting_balance >= 0", name="starting_balance_non_negative"),
        CheckConstraint("balance >= 0", name="balance_non_negative"),
    )


class PaperOrder(BaseModel, TimestampMixin):
    """One filled market order — every order in this feature fills
    immediately and completely; there is no pending/partial-fill state to
    track (see `PaperTradingService.place_order`'s own docstring).

    `raw_price` is the quote `app/paper_trading/pricing.py` resolved
    *before* slippage; `fill_price` is what the account was actually
    charged/credited — the difference is `slippage_applied`, always
    visible, never hidden inside a single opaque "price" column.
    `price_source`/`price_observed_at`/`is_stale_price` record exactly
    which real data the fill came from and how fresh it was, so a fill
    priced off a stale fallback candle is never presented as if it used a
    live, current price.
    """

    __tablename__ = "paper_orders"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    raw_price: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="The resolved quote price, before slippage.",
    )
    fill_price: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="What the account was actually charged/credited — raw_price with slippage applied.",
    )
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price_source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'ticker' | 'trade' | 'candle_close' — which real data this fill priced from.",
    )
    price_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the quote itself was observed (event_time, or the fallback candle's own "
        "open_time).",
    )
    is_stale_price: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if price_observed_at was already older than the staleness threshold at "
        "fill time.",
    )
    slippage_applied: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="abs(fill_price - raw_price) — always visible, never folded silently into "
        "fill_price.",
    )
    fee_applied: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    notional: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE), nullable=False, comment="fill_price * quantity."
    )
    realized_pnl: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=True,
        comment="Set only for a sell (this order's own contribution to realized PnL); NULL for "
        "a buy.",
    )

    __table_args__ = (
        CheckConstraint(f"side IN {ORDER_SIDES!r}", name="side_valid"),
        CheckConstraint(f"price_source IN {PRICE_SOURCES!r}", name="price_source_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )


class PaperPosition(BaseModel, TimestampMixin):
    """One account's materialized, currently-open holding in one symbol.

    Updated in place by every buy/sell against this symbol — never
    recomputed from `PaperOrder` history on read. A position that's fully
    closed (`quantity` reaches exactly `0`) is left in place at `quantity
    = 0` rather than deleted, so re-buying the same symbol later doesn't
    need to reinvent an identity; `PaperTradingService.list_positions`
    filters to `quantity > 0` (this platform's own "open positions" view).
    """

    __tablename__ = "paper_positions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    quantity: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False, default=0)
    average_entry_price: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE), nullable=False, default=0
    )

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_paper_positions_account_symbol"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
    )
