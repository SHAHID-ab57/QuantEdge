"""Paper Trading models — a virtual account, its filled orders, its
materialized open positions, and its optional automated strategy's own
decision log.

Market-orders-only. A position is **long or short**, optionally
**leveraged** (isolated margin only): `PaperPosition.side`/`leverage`/
`margin`/`liquidation_price` carry that state, and `PaperOrder.side` stays
the plain exchange verb (`buy`/`sell`) with `position_side` naming which
kind of position it acted on. Shorts and leverage are for **manually
placed orders only**. The one automated order path this feature supports
(`strategy_enabled` on `PaperAccount`, see its own field comments, and
`app.services.paper_trading_strategy.PaperTradingStrategyScheduler`) is not
a second order-placement path: it is "just another caller" of the exact
same `PaperTradingService.place_order` every manual order already goes
through, off by default, never able to open a position without a stop-loss
attached, and refused by that method for anything but an unleveraged long
(see `PaperTradingService._enforce_automated_restrictions`).

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
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
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
POSITION_SIDES = ("long", "short")
TRIGGER_REASONS = ("stop_loss", "take_profit", "liquidation")
TRIGGER_PRICE_BASES = ("mark", "last_fallback")
STRATEGY_DECISION_ACTIONS = ("opened", "closed", "no_action")


class PaperAccount(BaseModel, TimestampMixin):
    """One virtual trading account: its cash balance and cumulative realized PnL.

    `balance` is **available cash** only — opening a position posts margin
    out of it (tracked separately by `PaperPosition.margin`, not blended into
    this row), and closing releases margin plus realized PnL back into it. At
    1x leverage the margin is the whole notional, which is exactly the
    long-only cash accounting this engine started with. **Equity** (cash plus
    every position's margin plus its unrealized PnL at the live price) is
    never stored, since it depends on live prices; it is what the position,
    exposure and drawdown limits are measured against. `realized_pnl`
    accumulates the *actual* outcome of every order: an opening order's own
    fee (an immediate, certain cost) and, for a reducing order, its price PnL
    (`(fill_price - average_entry_price) * quantity - fee` for a long, the
    mirror image for a short), plus funding — see
    `app/services/paper_trading.py`'s own docstring for the full accounting
    model and why it reconciles exactly against `balance` once every
    position is flat. Unrealized PnL is never stored here — it depends on
    a live price lookup and is computed fresh on every read (`GET
    .../summary`).

    Pre-trade risk limits (`max_position_size_pct`/`max_exposure_pct`/
    `max_drawdown_pct`, each a percentage like `10` meaning 10%) and their
    running state (`peak_balance`, `trading_halted`) live on this same row
    — see `app/services/paper_trading.py`'s own docstring for exactly how
    each is computed and enforced, and why they're guarded by the same
    atomic `UPDATE ... WHERE` primitive `TrainingJobRepository
    .try_transition_to_running` established for its own check-then-act
    race (`PaperAccountRepository.try_apply_trade_effects`).
    """

    __tablename__ = "paper_accounts"

    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    starting_balance: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    balance: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    realized_pnl: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False, default=0)
    max_position_size_pct: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("10"),
        comment="A single order's resulting position value may never exceed this percentage of "
        "current balance.",
    )
    max_exposure_pct: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("50"),
        comment="Total open-position value (every symbol, at current prices) may never exceed "
        "this percentage of current balance.",
    )
    max_drawdown_pct: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("20"),
        comment="If account equity falls below peak_balance * (1 - this / 100), trading_halted "
        "is set.",
    )
    peak_balance: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="The highest account EQUITY (cash + margin + unrealized PnL) ever reached — "
        "never decreases. The column keeps its original name for API compatibility; it was a "
        "cash high-water mark before the drawdown limit moved to equity.",
    )
    trading_halted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Set once balance breaches the drawdown limit; does not clear itself on balance "
        "recovery — only an explicit resume-trading action clears it.",
    )
    max_leverage: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("5"),
        server_default="5",
        comment="The highest leverage any order on this account may use, manual or "
        "automated: the ceiling on a manual order's leverage and on the automated "
        "strategy's fixed strategy_leverage.",
    )
    state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Bumped by every guarded trade-effect update. The optimistic-concurrency guard "
        "matches on it, so it covers state (margin, positions, funding) that a balance "
        "comparison alone cannot see, e.g. a liquidation that forfeits margin without "
        "changing cash.",
    )
    strategy_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Opt-in automated strategy (app.services.paper_trading_strategy). Off by "
        "default — a researcher must explicitly enable it per account; there is no "
        "platform-wide default that turns it on.",
    )
    strategy_training_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="SET NULL"),
        nullable=True,
        comment="The training job the strategy requests a fresh prediction from every cycle — "
        "its own recorded symbol/timeframe is what the strategy trades, never a "
        "separately-configured one. Required whenever strategy_enabled is true (enforced "
        "in PaperTradingService.update_strategy_config, not by a DB constraint, since it "
        "depends on two columns together).",
    )
    strategy_confidence_threshold_pct: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("65"),
        server_default="65",
        comment="A fresh prediction's own confidence (0-1 probability, reported here as a % "
        "for consistency with every other risk/threshold field on this row) must reach at "
        "least this before the strategy acts on it at all.",
    )
    strategy_default_stop_loss_pct: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("5"),
        server_default="5",
        comment="Every automated entry attaches a stop-loss this % on the losing side of its "
        "own fill price (below a long's, above a short's) — tunable per account, but never "
        "omittable: an automated position without one is not a configuration this feature "
        "can express.",
    )
    strategy_leverage: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("2"),
        server_default="2",
        comment="The ONE leverage every automated entry uses, long or short. A fixed, "
        "per-account setting: it is never read from, scaled by, or derived from a "
        "prediction's confidence (which has been measured to carry no reliable relationship "
        "to being right). Must not exceed max_leverage.",
    )

    __table_args__ = (
        CheckConstraint("starting_balance >= 0", name="starting_balance_non_negative"),
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint("peak_balance >= 0", name="peak_balance_non_negative"),
        CheckConstraint("max_leverage >= 1 AND max_leverage <= 200", name="max_leverage_valid"),
        CheckConstraint(
            "strategy_leverage >= 1 AND strategy_leverage <= 200", name="strategy_leverage_valid"
        ),
        CheckConstraint(
            "max_position_size_pct > 0 AND max_position_size_pct <= 100",
            name="max_position_size_pct_valid",
        ),
        CheckConstraint(
            "max_exposure_pct > 0 AND max_exposure_pct <= 100", name="max_exposure_pct_valid"
        ),
        CheckConstraint(
            "max_drawdown_pct > 0 AND max_drawdown_pct <= 100", name="max_drawdown_pct_valid"
        ),
        CheckConstraint(
            "strategy_confidence_threshold_pct > 0 AND strategy_confidence_threshold_pct <= 100",
            name="strategy_confidence_threshold_pct_valid",
        ),
        CheckConstraint(
            "strategy_default_stop_loss_pct > 0 AND strategy_default_stop_loss_pct < 100",
            name="strategy_default_stop_loss_pct_valid",
        ),
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
    trigger_reason: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="'stop_loss' | 'take_profit' | 'liquidation' for a market-triggered auto-close; "
        "NULL for a manually-placed order.",
    )
    position_side: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="long",
        server_default="long",
        comment="'long' | 'short' — the kind of position this order opened, added to or reduced.",
    )
    leverage: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("1"),
        server_default="1",
        comment="The leverage of the position this order acted on.",
    )
    margin_applied: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        comment="Margin this order posted (opening/adding) or released (reducing/closing, "
        "before realized PnL); for a liquidation, the margin forfeited.",
    )
    reduce_only: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="The order was placed reduce-only: it could only shrink an existing position.",
    )
    gapped_through_bankruptcy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Liquidation only: the mark price had already passed the bankruptcy price, so "
        "the real loss would have exceeded the margin. The paper account's loss stays capped "
        "at the margin actually posted.",
    )
    trigger_price_basis: Mapped[str | None] = mapped_column(
        String(15),
        nullable=True,
        comment="'mark' | 'last_fallback' for a liquidation: the price the trigger used. A "
        "liquidation is meant to run on the mark price; 'last_fallback' records that no mark "
        "price was available and the last traded price stood in.",
    )

    __table_args__ = (
        CheckConstraint(f"side IN {ORDER_SIDES!r}", name="side_valid"),
        CheckConstraint(f"price_source IN {PRICE_SOURCES!r}", name="price_source_valid"),
        CheckConstraint(
            f"trigger_reason IS NULL OR trigger_reason IN {TRIGGER_REASONS!r}",
            name="trigger_reason_valid",
        ),
        CheckConstraint(f"position_side IN {POSITION_SIDES!r}", name="position_side_valid"),
        CheckConstraint(
            f"trigger_price_basis IS NULL OR trigger_price_basis IN {TRIGGER_PRICE_BASES!r}",
            name="trigger_price_basis_valid",
        ),
        CheckConstraint("leverage >= 1", name="order_leverage_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )


class PaperPosition(BaseModel, TimestampMixin):
    """One account's materialized, currently-open holding in one symbol.

    Updated in place by every order against this symbol — never
    recomputed from `PaperOrder` history on read. A position that's fully
    closed (`quantity` reaches exactly `0`) is left in place at `quantity
    = 0` rather than deleted, so re-buying the same symbol later doesn't
    need to reinvent an identity; `PaperTradingService.list_positions`
    filters to `quantity > 0` (this platform's own "open positions" view).

    `quantity` is always the *magnitude* (never negative); `side` says
    whether it is a long or a short. One row per `(account, symbol)`: a
    single net position, never a long and a short at once. `leverage` is
    fixed when the position opens, `margin` is the isolated margin posted
    against it (whole notional at 1x), and `liquidation_price` is the mark
    price at which the exchange would liquidate it (`NULL` for a long that
    cannot be, i.e. an unleveraged one) — recomputed whenever entry price,
    quantity or margin changes.

    `stop_loss_price`/`take_profit_price` are optional, nullable
    thresholds a researcher can set. For a long a stop-loss sits below the
    current price and a take-profit above it; for a short, the reverse —
    validated at set-time in `PaperTradingService`, never here, since
    "below/above current price" needs a live quote no DB constraint can see. Watched by
    `app.paper_trading.monitor.StopLossTakeProfitMonitor`, which closes
    the position automatically through the same fill logic a manual sell
    uses the instant either is crossed. Both are cleared back to `NULL`
    whenever a position is fully closed (`apply_sell` reaching `quantity
    == 0`) — a flat position has nothing left to protect, and a later
    re-buy of the same symbol at a completely different price would make
    a carried-over threshold meaningless.
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
    side: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="long",
        server_default="long",
        comment="'long' | 'short'. Meaningful only while quantity > 0.",
    )
    leverage: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("1"),
        server_default="1",
        comment="Fixed when the position was opened; 1 for an unleveraged position.",
    )
    margin: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        comment="Isolated margin posted against this position (its whole notional at 1x).",
    )
    liquidation_price: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=True,
        comment="The mark price at which this position is liquidated; NULL if it cannot be.",
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this position last went from flat to open — funding is only owed for "
        "funding times after it.",
    )
    stop_loss_price: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=True,
        comment="A long's stop-loss: closes at or below this price. A short's: at or above.",
    )
    take_profit_price: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=True,
        comment="A long's take-profit: closes at or above this price. A short's: at or below.",
    )

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_paper_positions_account_symbol"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint(f"side IN {POSITION_SIDES!r}", name="position_side_valid"),
        CheckConstraint("leverage >= 1", name="position_leverage_valid"),
        CheckConstraint("margin >= 0", name="margin_non_negative"),
        CheckConstraint(
            "stop_loss_price IS NULL OR stop_loss_price >= 0", name="stop_loss_price_non_negative"
        ),
        CheckConstraint(
            "take_profit_price IS NULL OR take_profit_price >= 0",
            name="take_profit_price_non_negative",
        ),
    )


class PaperStrategyDecision(BaseModel, TimestampMixin):
    """One automated-strategy cycle's own outcome for one account — acted
    on or not, and why. `app.services.paper_trading_strategy
    .PaperTradingStrategyScheduler` writes exactly one of these per
    strategy-enabled account, every tick, unconditionally: this is the
    "every decision is logged, including a no-op" requirement's actual
    storage, not a log line a researcher would need shell access to read
    — the Strategy panel's decision log reads this table directly
    (`GET .../strategy/decisions`).

    `predicted_value`/`confidence` are `NULL` together only when the
    cycle never got a prediction to reason about at all (the configured
    training job doesn't exist/isn't completed/has no recorded symbol,
    or the live prediction call itself raised) — `reason` always
    explains which. `direction` and `strategy_leverage` are recorded for
    every cycle too, acted on or not. `confidence_threshold_pct` is always recorded even
    then, snapshotting the account's own configured threshold *at the
    moment of this cycle*, so a later threshold change never rewrites
    the meaning of a past decision.

    `prediction_id`/`order_id` are both nullable, independently:
    a `no_action` decision reached after a real prediction still names
    it (`prediction_id` set, `order_id` null); one that opened or closed
    a position names both.
    """

    __tablename__ = "paper_strategy_decisions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="SET NULL"),
        nullable=True,
        comment="The job this cycle requested a prediction from — the account's own "
        "strategy_training_job_id at the moment of this cycle.",
    )
    symbol: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="The job's own recorded symbol; NULL only if the job itself couldn't be "
        "resolved this cycle (see reason).",
    )
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'opened' | 'closed' | 'no_action' — what this cycle actually did.",
    )
    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Plain-language explanation, always present — including for 'no_action'.",
    )
    predicted_value: Mapped[Any] = mapped_column(
        JSON,
        nullable=True,
        comment="The fresh prediction's own class label (or number, for a regressor); NULL if "
        "no prediction was obtained this cycle.",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="The fresh prediction's own confidence (0-1); NULL if unavailable or no "
        "prediction was obtained.",
    )
    confidence_threshold_pct: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="A snapshot of the account's own strategy_confidence_threshold_pct at the "
        "moment of this cycle — never re-read from the (possibly since-changed) account.",
    )
    direction: Mapped[str | None] = mapped_column(
        String(5),
        nullable=True,
        comment="'long' | 'short' — the side this cycle concerned: the position it opened or "
        "closed, or, for a no_action cycle, the side the model's call pointed at (up = long, "
        "down = short). NULL only when there was no directional call at all.",
    )
    strategy_leverage: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        default=Decimal("1"),
        server_default="1",
        comment="A snapshot of the account's own strategy_leverage at the moment of this "
        "cycle (rows from before leverage existed were 1x), never re-read from the "
        "possibly-since-changed account.",
    )
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paper_orders.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            f"action IN {STRATEGY_DECISION_ACTIONS!r}", name="paper_strategy_decision_action_valid"
        ),
        CheckConstraint(
            f"direction IS NULL OR direction IN {POSITION_SIDES!r}",
            name="decision_direction_valid",
        ),
    )


class PaperFundingSettlement(BaseModel, TimestampMixin):
    """One funding payment charged to (or credited to) one open position at
    one real funding time.

    Unique on `(account_id, symbol, funding_time)`: that key is what makes
    settlement idempotent, so a repeated or catch-up run after downtime can
    never charge the same position twice for the same funding time.
    `payment` is what the position *paid* (positive = a cost, negative = it
    received funding); `funding_rate` is stored as a **fraction** (the
    converted value, see `app.services.funding_rates`), never Delta's raw
    percent figure. `charged_to_margin` is the part of the payment the
    account's available cash could not cover, taken from the position's own
    margin instead (which moves its liquidation price).
    """

    __tablename__ = "paper_funding_settlements"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    funding_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position_side: Mapped[str] = mapped_column(String(5), nullable=False)
    quantity: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    index_price: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=False)
    funding_rate: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE), nullable=False, comment="Fraction per interval (0.0001 = 0.01%)."
    )
    payment: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="What the position paid; negative when it received funding.",
    )
    charged_to_margin: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE), nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        UniqueConstraint(
            "account_id", "symbol", "funding_time", name="uq_paper_funding_account_symbol_time"
        ),
        CheckConstraint(f"position_side IN {POSITION_SIDES!r}", name="funding_position_side_valid"),
    )
