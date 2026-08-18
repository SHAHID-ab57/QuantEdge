"""Typed Pydantic models for Delta Exchange WebSocket messages.

Field names mirror the compact wire keys documented by Delta (``p``
price, ``sy`` symbol, ``ts`` timestamp in microseconds). Fields whose
wire key is a Python keyword (``as``, ``is``) use aliases. Extra payload
fields are ignored. Convert microsecond timestamps to datetimes with
:func:`utc_from_micros`.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.ws.models import WSEvent


def utc_from_micros(micros: int) -> datetime:
    """Convert a Delta microsecond timestamp to a UTC datetime."""
    return datetime.fromtimestamp(micros / 1_000_000, tz=UTC)


class ChannelSubscription(BaseModel):
    """One channel entry in a ``subscriptions`` acknowledgement."""

    name: str
    symbols: list[str] | None = None
    error: str | None = None


class SubscriptionsEvent(WSEvent):
    """Server acknowledgement of the current subscription state."""

    channels: list[ChannelSubscription]


class KeyAuthEvent(WSEvent):
    """Server response to a ``key-auth`` request.

    ``status`` is one of ``authenticated``, ``incomplete_payload``,
    ``request_expired``, ``api_key_not_found``, ``invalid_signature``,
    ``ip_not_whitelisted``, or ``internal_server_error``.
    """

    success: bool
    status_code: int | None = None
    status: str | None = None
    message: str | None = None


class HeartbeatEvent(WSEvent):
    """Periodic server heartbeat (enabled via ``enable_heartbeat``)."""


class PongEvent(WSEvent):
    """Server response to a client ``ping``."""


class TickerData(BaseModel):
    """Per-symbol ticker payload for products aggregated in one frame."""

    s: str
    i: int | None = None
    m: Decimal | None = None
    m24hc: Decimal | None = None
    ohlc: list[Decimal] | None = None
    oi: list[Decimal] | None = None
    pb: list[Decimal] | None = None
    q: list[Decimal | None] | None = None
    g: list[Decimal | None] | None = None
    qiv: list[Decimal | None] | None = None
    to: list[Decimal] | None = None


class TickerEvent(WSEvent):
    """Top-of-book and 24h summary ticker update.

    Frames carry either a single symbol (``sy``/``sp``) or a ``d`` array
    of per-product entries.
    """

    sy: str | None = None
    sp: Decimal | None = None
    ts: int | None = None
    d: list[TickerData] | None = None


class OrderBookL1Event(WSEvent):
    """Best ask/bid update (``ob_l1`` channel)."""

    ap: Decimal
    ask_size: Decimal = Field(alias="as")
    bp: Decimal
    bid_size: Decimal = Field(alias="bs")
    lts: int | None = None
    sy: str
    ts: int


class OrderBookL2Event(WSEvent):
    """Top-15 level orderbook snapshot (``ob_l2`` channel).

    ``a`` and ``b`` hold ``[price, size]`` pairs for asks and bids.
    """

    a: list[list[Decimal]] | None = None
    b: list[list[Decimal]] | None = None
    sy: str
    ts: int


class OrderBookUpdatesEvent(WSEvent):
    """Incremental orderbook update (``ob_updates`` channel).

    The first frame has ``action`` ``snapshot``; follow-up frames carry
    ``seq`` that must be contiguous per symbol.
    """

    action: str
    seq: int | None = None
    cs: int | None = None
    a: list[list[Decimal]] | None = None
    b: list[list[Decimal]] | None = None
    sy: str
    ts: int


class TradesEvent(WSEvent):
    """A real-time trade fill (``trades`` channel)."""

    p: Decimal
    r: Literal["m", "t"]
    s: Decimal
    sy: str
    t: int
    ts: int


class MarkPriceEvent(WSEvent):
    """A mark price update (``mark_price`` channel, ``MARK:`` symbols)."""

    p: Decimal
    sy: str
    ts: int


class CandlestickEvent(WSEvent):
    """The latest OHLC candle for a resolution (``candlestick_*``)."""

    c: Decimal
    h: Decimal
    low: Decimal = Field(alias="l")
    o: Decimal
    res: str
    sy: str
    ts: int
    v: Decimal | None = None


class SpotPriceEvent(WSEvent):
    """An underlying index price update (``spot_price`` channel)."""

    p: Decimal
    sy: str
    ts: int


class SpotTwapPriceEvent(WSEvent):
    """A 30-minute TWAP of an underlying index (``spot_30mtwap_price``).

    Note this channel uses the long field names (``symbol``, ``price``,
    ``timestamp``) instead of the compact keys used elsewhere.
    """

    symbol: str
    price: Decimal
    timestamp: int


class FundingRateEvent(WSEvent):
    """A funding rate update (``funding_rate`` channel)."""

    fi: int
    fr: Decimal
    nfr: int
    sy: str
    ts: int


class ProductUpdate(BaseModel):
    """Product affected by a ``product_updates`` event."""

    id: int | None = None
    symbol: str | None = None
    trading_status: str | None = None


class ProductUpdatesEvent(WSEvent):
    """Market disruption or auction event (``product_updates`` channel)."""

    event: str | None = None
    product: ProductUpdate | None = None
    timestamp: int | None = None


class SystemStatusEvent(WSEvent):
    """Exchange status change (``system_status`` channel)."""

    status: str | None = None
    event: str | None = None
    timestamp: int | None = None
    maintenance_start_time: int | None = None
    maintenance_announcement_time: int | None = None
    maintenance_finish_time: int | None = None


class PositionUpdate(BaseModel):
    """One entry of a ``positions`` snapshot."""

    adl_level: str | None = None
    auto_topup: bool | None = None
    bankruptcy_price: Decimal | None = None
    commission: Decimal | None = None
    created_at: str | None = None
    entry_price: Decimal | None = None
    liquidation_price: Decimal | None = None
    margin: Decimal | None = None
    product_id: int | None = None
    product_symbol: str | None = None
    realized_funding: Decimal | None = None
    realized_pnl: Decimal | None = None
    size: int | None = None
    updated_at: str | None = None
    user_id: int | None = None
    symbol: str | None = None


class PositionsEvent(WSEvent):
    """Position update or snapshot (private ``positions`` channel)."""

    action: str | None = None
    reason: str | None = None
    symbol: str | None = None
    product_id: int | None = None
    size: int | None = None
    margin: Decimal | None = None
    entry_price: Decimal | None = None
    liquidation_price: Decimal | None = None
    bankruptcy_price: Decimal | None = None
    commission: Decimal | None = None
    result: list[PositionUpdate] | None = None


class OrdersEvent(WSEvent):
    """Order update (private ``orders`` channel).

    ``reason`` distinguishes fills, stop updates/triggers, cancellations,
    liquidations, and self-trades.
    """

    action: str | None = None
    reason: str | None = None
    symbol: str | None = None
    product_id: int | None = None
    order_id: int | None = None
    client_order_id: str | None = None
    size: Decimal | None = None
    unfilled_size: Decimal | None = None
    average_fill_price: Decimal | None = None
    limit_price: Decimal | None = None
    side: Literal["buy", "sell"] | str | None = None
    cancellation_reason: str | None = None
    stop_order_type: str | None = None
    bracket_order: bool | None = None
    state: str | None = None
    seq_no: int | None = None
    timestamp: int | None = None
    stop_price: Decimal | None = None
    trigger_price_max_or_min: Decimal | None = None
    bracket_stop_loss_price: Decimal | None = None
    bracket_stop_loss_limit_price: Decimal | None = None
    bracket_take_profit_price: Decimal | None = None
    bracket_take_profit_limit_price: Decimal | None = None
    bracket_trail_amount: Decimal | None = None


class UserTradesEvent(WSEvent):
    """User trade fill update (private ``user_trades`` channel).

    Best-effort typing; unmodeled fields are ignored.
    """

    action: str | None = None
    symbol: str | None = None
    size: Decimal | None = None
    timestamp: int | None = None


class MarginsEvent(WSEvent):
    """Wallet balance update (private ``margins`` channel)."""

    asset: str | None = None
    wallet_balance: Decimal | None = None
    available_balance: Decimal | None = None
    realized_pnl: Decimal | None = None
    realized_funding: Decimal | None = None
    portfolio_margin: Decimal | None = None
    timestamp: int | None = None
