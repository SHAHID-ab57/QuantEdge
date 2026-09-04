"""Wire schemas (DTOs) for the Paper Trading API.

Same split as every other domain on this platform: `app/paper_trading/`
stays framework/database-free, and this module is the one place an order
request is validated and a response is assembled.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_serializer

if TYPE_CHECKING:
    from app.models.paper_trading import PaperAccount, PaperOrder, PaperPosition


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal `Z`, matching every timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class PaperAccountCreateRequest(BaseModel):
    """Open a new virtual trading account with a starting cash balance."""

    name: str | None = Field(default=None, max_length=200)
    starting_balance: Decimal = Field(..., gt=0, description="Starting cash balance")


class PaperAccountResponse(BaseModel):
    """One paper trading account's own identity and cash balance."""

    id: str
    name: str | None
    starting_balance: Decimal
    balance: Decimal
    realized_pnl: Decimal
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, account: "PaperAccount") -> "PaperAccountResponse":
        return cls(
            id=str(account.id),
            name=account.name,
            starting_balance=account.starting_balance,
            balance=account.balance,
            realized_pnl=account.realized_pnl,
            created_at=account.created_at,
        )


class PaperAccountListResponse(BaseModel):
    """Every paper trading account this platform has recorded, most recently created first."""

    accounts: list[PaperAccountResponse]
    total: int
    limit: int
    offset: int


class PaperOrderRequest(BaseModel):
    """Place one market order — long-only: a buy opens/adds to a position,
    a sell reduces/closes one; there is no short side."""

    symbol: str = Field(..., description="Market to trade")
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(..., gt=0, description="Order quantity, in the base asset")


class PaperOrderResponse(BaseModel):
    """One filled market order — every order fills immediately and
    completely; there is no pending/partial state."""

    id: str
    account_id: str
    symbol: str
    side: Literal["buy", "sell"]
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
    quantity: Decimal
    average_entry_price: Decimal
    current_price: Decimal
    price_source: Literal["ticker", "trade", "candle_close"]
    unrealized_pnl: Decimal = Field(
        description="(current_price - average_entry_price) * quantity — no slippage/fee applied; "
        "a mark-to-market valuation, not a hypothetical exit fill"
    )

    @classmethod
    def from_model(
        cls, position: "PaperPosition", *, current_price: Decimal, price_source: str
    ) -> "PaperPositionDTO":
        unrealized_pnl = (current_price - Decimal(position.average_entry_price)) * Decimal(
            position.quantity
        )
        return cls(
            symbol=position.symbol,
            quantity=position.quantity,
            average_entry_price=position.average_entry_price,
            current_price=current_price,
            price_source=price_source,  # type: ignore[arg-type]
            unrealized_pnl=unrealized_pnl,
        )


class PaperPositionListResponse(BaseModel):
    """Every symbol this account currently holds."""

    positions: list[PaperPositionDTO]


class PortfolioSummaryResponse(BaseModel):
    """An account's own balance, realized PnL, and live unrealized PnL —
    the account summary card's data source."""

    account_id: str
    balance: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal = Field(description="Summed across every currently-open position")
    total_equity: Decimal = Field(
        description="balance + the live mark-to-market value of every open position"
    )
    open_position_count: int


__all__ = [
    "PaperAccountCreateRequest",
    "PaperAccountListResponse",
    "PaperAccountResponse",
    "PaperOrderListResponse",
    "PaperOrderRequest",
    "PaperOrderResponse",
    "PaperPositionDTO",
    "PaperPositionListResponse",
    "PortfolioSummaryResponse",
]
