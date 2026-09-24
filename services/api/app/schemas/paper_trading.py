"""Wire schemas (DTOs) for the Paper Trading API.

Same split as every other domain on this platform: `app/paper_trading/`
stays framework/database-free, and this module is the one place an order
request is validated and a response is assembled.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_serializer, model_validator

if TYPE_CHECKING:
    from app.models.paper_trading import (
        PaperAccount,
        PaperFundingSettlement,
        PaperOrder,
        PaperPosition,
        PaperStrategyDecision,
    )


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal `Z`, matching every timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class PaperAccountCreateRequest(BaseModel):
    """Open a new virtual trading account with a starting cash balance.

    The three risk-limit percentages fall back to this platform's
    configured defaults (`app/core/config.py`) when omitted — override
    them per account only when a specific test or scenario needs a
    different threshold than the platform default.
    """

    name: str | None = Field(default=None, max_length=200)
    starting_balance: Decimal = Field(..., gt=0, description="Starting cash balance")
    max_position_size_pct: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
        description="Max % of current balance a single position's value may reach. "
        "Defaults to this platform's configured threshold when omitted.",
    )
    max_exposure_pct: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
        description="Max % of current balance total open-position value may reach. "
        "Defaults to this platform's configured threshold when omitted.",
    )
    max_drawdown_pct: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
        description="Max % account equity may fall below its peak before trading halts. "
        "Defaults to this platform's configured threshold when omitted.",
    )
    max_leverage: Decimal | None = Field(
        default=None,
        ge=1,
        le=200,
        description="The highest leverage any order may use on this account (Delta's own "
        "ceiling is 200x), and the ceiling on the automated strategy's fixed leverage. "
        "Defaults to this platform's configured, deliberately conservative value when omitted.",
    )


class PaperAccountResponse(BaseModel):
    """One paper trading account's own identity, cash balance, and risk limits."""

    id: str
    name: str | None
    starting_balance: Decimal
    balance: Decimal
    realized_pnl: Decimal
    max_position_size_pct: Decimal
    max_exposure_pct: Decimal
    max_drawdown_pct: Decimal
    max_leverage: Decimal
    peak_balance: Decimal = Field(
        description="The highest account equity ever reached (the drawdown limit's reference)"
    )
    trading_halted: bool
    strategy_enabled: bool = Field(
        description="Opt-in automated strategy — off by default, per-account"
    )
    strategy_training_job_id: str | None = Field(
        default=None,
        description="The training job the strategy predicts from; required whenever "
        "strategy_enabled is true",
    )
    strategy_confidence_threshold_pct: Decimal = Field(
        description="A fresh prediction must reach at least this % confidence before the "
        "strategy acts"
    )
    strategy_default_stop_loss_pct: Decimal = Field(
        description="Every automated entry attaches a stop-loss this % on the losing side of "
        "its own fill price (below a long's, above a short's)"
    )
    strategy_volatility_training_job_id: str | None = Field(
        default=None,
        description="The logistic_regression job whose fresh volatility_regime forecast "
        "scales a new automated entry's stop-loss width; null means every entry uses "
        "strategy_default_stop_loss_pct unscaled",
    )
    strategy_leverage: Decimal = Field(
        description="The one fixed leverage every automated entry uses, long or short — never "
        "derived from a prediction's confidence"
    )
    strategy_paused_reason: Literal["feature_drift"] | None = Field(
        default=None,
        description="Set only when the scheduler itself — never a human — disabled the "
        "strategy (today: only 'feature_drift'). Null when strategy_enabled is false because "
        "a human turned it off, or when the strategy has never been auto-paused.",
    )
    strategy_paused_at: datetime | None = Field(
        default=None, description="When strategy_paused_reason was set; null exactly when it is"
    )
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso(value)

    @field_serializer("strategy_paused_at")
    def _serialize_strategy_paused_at(self, value: datetime | None) -> str | None:
        return _iso(value) if value is not None else None

    @classmethod
    def from_model(cls, account: "PaperAccount") -> "PaperAccountResponse":
        return cls(
            id=str(account.id),
            name=account.name,
            starting_balance=account.starting_balance,
            balance=account.balance,
            realized_pnl=account.realized_pnl,
            max_position_size_pct=account.max_position_size_pct,
            max_exposure_pct=account.max_exposure_pct,
            max_drawdown_pct=account.max_drawdown_pct,
            max_leverage=account.max_leverage,
            peak_balance=account.peak_balance,
            trading_halted=account.trading_halted,
            strategy_enabled=account.strategy_enabled,
            strategy_training_job_id=(
                str(account.strategy_training_job_id)
                if account.strategy_training_job_id is not None
                else None
            ),
            strategy_confidence_threshold_pct=account.strategy_confidence_threshold_pct,
            strategy_default_stop_loss_pct=account.strategy_default_stop_loss_pct,
            strategy_volatility_training_job_id=(
                str(account.strategy_volatility_training_job_id)
                if account.strategy_volatility_training_job_id is not None
                else None
            ),
            strategy_leverage=account.strategy_leverage,
            strategy_paused_reason=account.strategy_paused_reason,  # type: ignore[arg-type]
            strategy_paused_at=account.strategy_paused_at,
            created_at=account.created_at,
        )


class PaperAccountListResponse(BaseModel):
    """Every paper trading account this platform has recorded, most recently created first."""

    accounts: list[PaperAccountResponse]
    total: int
    limit: int
    offset: int


class PaperOrderRequest(BaseModel):
    """Place one market order.

    In a single net position per market, a **buy** opens or adds to a long,
    or reduces a short; a **sell** opens or adds to a short, or reduces a
    long. An order larger than the position it reduces is rejected rather
    than carried through zero into the opposite side.

    `leverage` (isolated margin) is fixed when a position opens: omit it
    to open at 1x, or to add to / reduce an existing position. It may not
    exceed the account's `max_leverage`. Shorts, leverage and `reduce_only`
    are for manually placed orders; the automated strategy is refused
    anything but an unleveraged long.

    `stop_loss_price`/`take_profit_price` are optional and only meaningful
    on an order that opens or adds to a position (a reducing order has
    nothing left to protect). Provide a value to set it on the resulting
    position; omit it to leave that position's existing threshold (if any)
    unchanged — omitting is *not* the same as clearing, which is only
    possible via `PATCH .../positions/{symbol}`'s explicit `null`. A long's
    stop-loss sits below the current price and its take-profit above; a
    short's are the reverse, and a stop-loss must lie on the safe side of the
    position's liquidation price. Both are validated against the current
    price (and each other) the instant this order fills.
    """

    symbol: str = Field(..., description="Market to trade")
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(..., gt=0, description="Order quantity, in the base asset")
    leverage: Decimal | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Leverage for a position this order opens; omit to use 1x (or to keep "
        "an existing position's own)",
    )
    reduce_only: bool = Field(
        default=False,
        description="If true, the order may only shrink an existing position; it is rejected "
        "rather than opening or adding to one",
    )
    stop_loss_price: Decimal | None = Field(
        default=None, gt=0, description="Set on the resulting position — opening/adding only"
    )
    take_profit_price: Decimal | None = Field(
        default=None, gt=0, description="Set on the resulting position — opening/adding only"
    )

    @model_validator(mode="after")
    def _reject_thresholds_on_a_reduce_only_order(self) -> "PaperOrderRequest":
        if self.reduce_only and (
            self.stop_loss_price is not None or self.take_profit_price is not None
        ):
            raise ValueError(
                "stop_loss_price/take_profit_price only apply to an order that opens or adds "
                "to a position — a reduce-only order has nothing left to protect"
            )
        return self


class PaperOrderResponse(BaseModel):
    """One filled market order — every order fills immediately and
    completely; there is no pending/partial state."""

    id: str
    account_id: str
    symbol: str
    side: Literal["buy", "sell"]
    position_side: Literal["long", "short"] = Field(
        description="The kind of position this order opened, added to or reduced"
    )
    leverage: Decimal = Field(description="The leverage of the position this order acted on")
    margin_applied: Decimal = Field(
        description="Margin this order posted (opening/adding) or released (reducing/closing); "
        "for a liquidation, the margin forfeited"
    )
    reduce_only: bool
    quantity: Decimal
    raw_price: Decimal = Field(description="The resolved quote, before slippage")
    fill_price: Decimal = Field(description="What the account was actually charged/credited")
    fill_time: datetime
    price_source: Literal["ticker", "trade", "candle_close"]
    price_observed_at: datetime = Field(
        description="When the quote itself was observed — a live event_time, or a fallback "
        "candle's own open_time"
    )
    is_stale_price: bool = Field(
        description="True if the quote was already older than the staleness threshold at fill time"
    )
    slippage_applied: Decimal
    fee_applied: Decimal
    notional: Decimal = Field(description="fill_price * quantity")
    realized_pnl: Decimal | None = Field(
        default=None, description="This order's own contribution to realized PnL; null for a buy"
    )
    trigger_reason: Literal["stop_loss", "take_profit", "liquidation"] | None = Field(
        default=None,
        description="Set when this order was a market-triggered auto-close, not a manually "
        "placed one; null for every ordinary order",
    )
    gapped_through_bankruptcy: bool = Field(
        default=False,
        description="Liquidation only: the mark price had already passed the bankruptcy "
        "price. The paper account's loss stays capped at the margin it posted",
    )
    trigger_price_basis: Literal["mark", "last_fallback"] | None = Field(
        default=None,
        description="Liquidation only: 'mark' (the intended basis), or 'last_fallback' if no "
        "mark price was available and the last traded price stood in",
    )
    created_at: datetime

    @field_serializer("fill_time", "price_observed_at", "created_at")
    def _serialize_timestamps(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, order: "PaperOrder") -> "PaperOrderResponse":
        return cls(
            id=str(order.id),
            account_id=str(order.account_id),
            symbol=order.symbol,
            side=order.side,  # type: ignore[arg-type]
            position_side=order.position_side,  # type: ignore[arg-type]
            leverage=order.leverage,
            margin_applied=order.margin_applied,
            reduce_only=order.reduce_only,
            quantity=order.quantity,
            raw_price=order.raw_price,
            fill_price=order.fill_price,
            fill_time=order.fill_time,
            price_source=order.price_source,  # type: ignore[arg-type]
            price_observed_at=order.price_observed_at,
            is_stale_price=order.is_stale_price,
            slippage_applied=order.slippage_applied,
            fee_applied=order.fee_applied,
            notional=order.notional,
            realized_pnl=order.realized_pnl,
            trigger_reason=order.trigger_reason,  # type: ignore[arg-type]
            gapped_through_bankruptcy=order.gapped_through_bankruptcy,
            trigger_price_basis=order.trigger_price_basis,  # type: ignore[arg-type]
            created_at=order.created_at,
        )


class PaperOrderListResponse(BaseModel):
    """One page of an account's own order history."""

    orders: list[PaperOrderResponse]
    total: int
    limit: int
    offset: int


class PaperPositionDTO(BaseModel):
    """One currently-open holding, marked to the same live price a fill would use."""

    symbol: str
    side: Literal["long", "short"]
    quantity: Decimal = Field(description="Position size (always positive; `side` gives direction)")
    average_entry_price: Decimal
    leverage: Decimal
    margin: Decimal = Field(description="Isolated margin posted against this position")
    liquidation_price: Decimal | None = Field(
        default=None,
        description="The mark price at which the position is liquidated; null if it cannot be "
        "(an unleveraged long)",
    )
    liquidation_distance_pct: Decimal | None = Field(
        default=None,
        description="How far the live price is from the liquidation price, as a % of the "
        "live price; null when there is no liquidation price",
    )
    current_price: Decimal
    price_source: Literal["ticker", "trade", "candle_close"]
    unrealized_pnl: Decimal = Field(
        description="A long: (current_price - average_entry_price) * quantity. A short: "
        "(average_entry_price - current_price) * quantity. No slippage/fee applied; a "
        "mark-to-market valuation, not a hypothetical exit fill"
    )
    stop_loss_price: Decimal | None = Field(
        default=None,
        description="Auto-closes the position when the price falls to (long) or rises to "
        "(short) this level; null if unset",
    )
    take_profit_price: Decimal | None = Field(
        default=None,
        description="Auto-closes the position when the price rises to (long) or falls to "
        "(short) this level; null if unset",
    )

    @classmethod
    def from_model(
        cls, position: "PaperPosition", *, current_price: Decimal, price_source: str
    ) -> "PaperPositionDTO":
        from app.paper_trading.margin import unrealized_pnl

        side = position.side
        pnl = unrealized_pnl(
            side=side,  # type: ignore[arg-type]
            entry_price=Decimal(position.average_entry_price),
            price=current_price,
            quantity=Decimal(position.quantity),
        )
        liquidation = (
            Decimal(position.liquidation_price) if position.liquidation_price is not None else None
        )
        distance = (
            abs(current_price - liquidation) / current_price * Decimal(100)
            if liquidation is not None and current_price > 0
            else None
        )
        return cls(
            symbol=position.symbol,
            side=side,  # type: ignore[arg-type]
            quantity=position.quantity,
            average_entry_price=position.average_entry_price,
            leverage=position.leverage,
            margin=position.margin,
            liquidation_price=liquidation,
            liquidation_distance_pct=distance,
            current_price=current_price,
            price_source=price_source,  # type: ignore[arg-type]
            unrealized_pnl=pnl,
            stop_loss_price=position.stop_loss_price,
            take_profit_price=position.take_profit_price,
        )


class PositionThresholdsUpdateRequest(BaseModel):
    """Set, update, or clear a position's stop-loss/take-profit.

    Only fields actually present in the request body are changed — send
    an explicit `null` to clear one, omit a field entirely to leave it
    exactly as it is. The service layer reads `model_fields_set` to tell
    "omitted" from "explicitly null" apart (both parse to the same `None`
    otherwise) — the same `exclude_unset` partial-update idiom
    `ExperimentService.update` already uses.
    """

    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    take_profit_price: Decimal | None = Field(default=None, gt=0)


class PaperPositionListResponse(BaseModel):
    """Every symbol this account currently holds."""

    positions: list[PaperPositionDTO]


class PortfolioSummaryResponse(BaseModel):
    """An account's own available cash, realized PnL, and live unrealized PnL —
    the account summary card's data source."""

    account_id: str
    balance: Decimal = Field(description="Available cash (margin already posted is not included)")
    realized_pnl: Decimal = Field(description="Realized trading PnL, net of fees and funding")
    unrealized_pnl: Decimal = Field(description="Summed across every currently-open position")
    margin_in_use: Decimal = Field(description="Isolated margin posted across every open position")
    total_equity: Decimal = Field(
        description="balance + margin in use + unrealized PnL: cash plus the live "
        "mark-to-market value of every open position"
    )
    total_notional: Decimal = Field(
        description="Sum of every open position's notional at the live price"
    )
    effective_leverage: Decimal = Field(description="total_notional / total_equity")
    open_position_count: int


class RiskSummaryResponse(BaseModel):
    """An account's own pre-trade risk state — current exposure and
    drawdown against their configured limits, and whether trading is
    halted. The Risk Summary panel's data source.

    Exposure and drawdown are measured on **equity** (cash + margin +
    unrealized PnL at live prices), and exposure on **notional** at live
    prices, never on cash: cash falls whenever margin is posted, with no
    loss at all.

    `current_position_size_pct`/distance is deliberately not included:
    the position-sizing limit is checked per order against one symbol's
    own resulting value (there is no single account-wide "current" figure
    for it) — `max_position_size_pct` itself is still reported so its
    threshold is visible even though it has no single "current %" to pair
    with the way exposure and drawdown do.
    """

    account_id: str
    balance: Decimal = Field(description="Available cash")
    equity: Decimal = Field(description="Cash + margin in use + unrealized PnL at live prices")
    margin_in_use: Decimal
    peak_balance: Decimal = Field(description="The highest account equity ever reached")
    total_notional: Decimal = Field(description="Sum of open positions' notional at live prices")
    effective_leverage: Decimal = Field(description="total_notional / equity")
    current_exposure_pct: Decimal = Field(
        description="Total open notional (live prices) as a % of current equity"
    )
    max_exposure_pct: Decimal
    exposure_headroom_pct: Decimal = Field(
        description="max_exposure_pct - current_exposure_pct; how much % room remains"
    )
    current_drawdown_pct: Decimal = Field(
        description="How far current equity has fallen below its peak, as a %"
    )
    max_drawdown_pct: Decimal
    drawdown_headroom_pct: Decimal = Field(
        description="max_drawdown_pct - current_drawdown_pct; how much % room remains"
    )
    max_position_size_pct: Decimal
    max_leverage: Decimal
    trading_halted: bool


class PaperFundingSettlementResponse(BaseModel):
    """One funding payment charged to, or received by, an open position."""

    id: str
    account_id: str
    symbol: str
    funding_time: datetime
    position_side: Literal["long", "short"]
    quantity: Decimal
    index_price: Decimal
    funding_rate: Decimal = Field(description="A fraction per interval (0.0001 = 0.01%)")
    payment: Decimal = Field(description="What the position paid; negative when it received")
    charged_to_margin: Decimal = Field(
        description="The part of the payment available cash could not cover, taken from the "
        "position's margin (which moves its liquidation price)"
    )

    @field_serializer("funding_time")
    def _serialize_funding_time(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, row: "PaperFundingSettlement") -> "PaperFundingSettlementResponse":
        return cls(
            id=str(row.id),
            account_id=str(row.account_id),
            symbol=row.symbol,
            funding_time=row.funding_time,
            position_side=row.position_side,  # type: ignore[arg-type]
            quantity=row.quantity,
            index_price=row.index_price,
            funding_rate=row.funding_rate,
            payment=row.payment,
            charged_to_margin=row.charged_to_margin,
        )


class PaperFundingSettlementListResponse(BaseModel):
    """One page of an account's funding settlements, most recent first."""

    settlements: list[PaperFundingSettlementResponse]
    total: int
    limit: int
    offset: int


class PaperStrategyConfigUpdateRequest(BaseModel):
    """Enable/disable the automated strategy and tune its threshold/stop-loss.

    The same partial-update idiom `PositionThresholdsUpdateRequest` uses:
    only fields actually present in the request body are changed (the
    service reads `model_fields_set`) — send an explicit `null` for
    `training_job_id` to clear it, omit a field entirely to leave it
    exactly as it is. Validated against the *final*, merged state: you
    cannot enable the strategy in the same request that clears its
    training job, and you cannot clear the training job of an account
    that's already enabled without disabling it first (or in the same
    request).
    """

    enabled: bool | None = Field(default=None, description="Turn the automated strategy on/off")
    training_job_id: uuid.UUID | None = Field(
        default=None, description="The completed, real-data job to predict from"
    )
    volatility_training_job_id: uuid.UUID | None = Field(
        default=None,
        description="VOLATILITY-STOP-WIDTH (Option B): the logistic_regression job whose "
        "fresh volatility_regime forecast scales a new automated entry's stop-loss width. "
        "Null (the default) means unscaled — every entry uses default_stop_loss_pct as-is, "
        "exactly as before this field existed. Not validated against model_type/symbol at "
        "write time; an unsuitable job is a runtime fail-closed case, not a rejected "
        "configuration.",
    )
    confidence_threshold_pct: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
        description="A fresh prediction must reach at least this % confidence to act on",
    )
    default_stop_loss_pct: Decimal | None = Field(
        default=None,
        gt=0,
        lt=100,
        description="Every automated entry attaches a stop-loss this % on the losing side of "
        "its own fill price (below a long's, above a short's); must sit inside the liquidation "
        "distance of the strategy's leverage",
    )
    leverage: Decimal | None = Field(
        default=None,
        ge=1,
        le=200,
        description="The one fixed leverage every automated entry uses, long or short. Never "
        "derived from a prediction's confidence; must not exceed the account's max_leverage",
    )

    @model_validator(mode="after")
    def _reject_explicit_null_thresholds(self) -> "PaperStrategyConfigUpdateRequest":
        """Unlike `training_job_id` (which has real "clear" semantics —
        `NULL` is a valid, meaningful state), `confidence_threshold_pct`/
        `default_stop_loss_pct` never do: this account always has *some*
        threshold/stop-loss percentage in force, never none at all. `gt=0`
        only constrains a *given* Decimal — Pydantic does not apply it to
        an explicit `null` on an `Optional` field, so `{"default_stop_loss_pct":
        null}` would otherwise parse successfully and reach the service
        layer's `Decimal(None)` call, raising an unhandled `TypeError`
        (a raw 500) instead of the clean 400 this rejects it with instead.
        `model_fields_set` is what distinguishes this from the ordinary,
        valid "omitted entirely, leave unchanged" case — both parse to the
        same `None` otherwise.
        """
        if (
            "confidence_threshold_pct" in self.model_fields_set
            and self.confidence_threshold_pct is None
        ):
            raise ValueError(
                "confidence_threshold_pct cannot be explicitly cleared to null — omit it "
                "entirely to leave it unchanged"
            )
        if "default_stop_loss_pct" in self.model_fields_set and self.default_stop_loss_pct is None:
            raise ValueError(
                "default_stop_loss_pct cannot be explicitly cleared to null — omit it "
                "entirely to leave it unchanged"
            )
        if "leverage" in self.model_fields_set and self.leverage is None:
            raise ValueError(
                "leverage cannot be explicitly cleared to null — omit it entirely to leave "
                "it unchanged"
            )
        return self


class PaperStrategyDecisionResponse(BaseModel):
    """One automated-strategy cycle's own outcome — acted on or not, and why."""

    id: str
    account_id: str
    training_job_id: str | None
    symbol: str | None
    action: Literal["opened", "closed", "no_action"]
    reason: str
    predicted_value: Any | None = Field(
        default=None, description="The class label (or number) the fresh prediction returned"
    )
    confidence: float | None = Field(
        default=None, description="The fresh prediction's own confidence (0-1)"
    )
    confidence_threshold_pct: Decimal = Field(
        description="The account's configured threshold at the moment of this cycle"
    )
    direction: Literal["long", "short"] | None = Field(
        default=None,
        description="The side this cycle concerned: the position it opened or closed, or, for a "
        "no_action cycle, the side the model's call pointed at (up = long, down = short); null "
        "only when there was no directional call",
    )
    strategy_leverage: Decimal = Field(
        description="The account's fixed strategy leverage at the moment of this cycle"
    )
    prediction_id: str | None = None
    order_id: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, decision: "PaperStrategyDecision") -> "PaperStrategyDecisionResponse":
        return cls(
            id=str(decision.id),
            account_id=str(decision.account_id),
            training_job_id=(
                str(decision.training_job_id) if decision.training_job_id is not None else None
            ),
            symbol=decision.symbol,
            action=decision.action,  # type: ignore[arg-type]
            reason=decision.reason,
            predicted_value=decision.predicted_value,
            confidence=decision.confidence,
            confidence_threshold_pct=decision.confidence_threshold_pct,
            direction=decision.direction,  # type: ignore[arg-type]
            strategy_leverage=decision.strategy_leverage,
            prediction_id=(
                str(decision.prediction_id) if decision.prediction_id is not None else None
            ),
            order_id=str(decision.order_id) if decision.order_id is not None else None,
            created_at=decision.created_at,
        )


class PaperStrategyDecisionListResponse(BaseModel):
    """One page of an account's own strategy decision log, most recent first."""

    decisions: list[PaperStrategyDecisionResponse]
    total: int
    limit: int
    offset: int


__all__ = [
    "PaperAccountCreateRequest",
    "PaperAccountListResponse",
    "PaperAccountResponse",
    "PaperFundingSettlementListResponse",
    "PaperFundingSettlementResponse",
    "PaperOrderListResponse",
    "PaperOrderRequest",
    "PaperOrderResponse",
    "PaperPositionDTO",
    "PaperPositionListResponse",
    "PaperStrategyConfigUpdateRequest",
    "PaperStrategyDecisionListResponse",
    "PaperStrategyDecisionResponse",
    "PortfolioSummaryResponse",
    "PositionThresholdsUpdateRequest",
    "RiskSummaryResponse",
]
