"""Price resolution and the slippage/fee execution model.

Realistic execution is the one thing this feature exists to guarantee: a
market order never fills at a perfect, cost-free price. An unrealistically
generous simulation is worse than none — it looks like evidence. Every
fill applies a modeled slippage and fee; neither is ever skipped, and both
are always reported on the resulting order, never folded silently into one
opaque price.

**The slippage/fee model, documented plainly**: a simple fixed-basis-point
model, per this feature's own spec — no order-book depth, no liquidity
curve, no venue-specific fee tier. `PAPER_TRADING_SLIPPAGE_BPS` moves the
fill price *against* the trader (a buy fills higher, a sell fills lower)
by that many basis points off the resolved quote; `PAPER_TRADING_FEE_BPS`
charges that many basis points of the fill's own notional (`fill_price *
quantity`) as a fee, always a cost, never a rebate. Both are settings
(`app/core/config.py`), not hardcoded, so a test can assert the *exact*
modeled amount rather than a hardcoded expectation that could silently
drift from the code.

**Price resolution — the same real data every other live feature reads
from, never a second market-data path**: `MarketStateManager.get_latest_
ticker`/`get_latest_trade` (the identical live state
`app/api/v1/endpoints/market_stream.py`'s own WebSocket gateway reads,
via `app/runtime.py`'s process-wide singleton) when live data is flowing;
falling back to the latest stored candle's own close — at the *finest*
timeframe actually stored for this symbol, via `resolution_duration`
(reused, not re-derived) — when it isn't. Every quote's own `observed_at`
is compared against `paper_trading_stale_price_threshold_seconds`
(default 300s) and marked `is_stale` if it's older — a fill priced off a
stale fallback candle is never presented as if it used a live, current
price.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.paper_trading.base import FillQuote, FillResult, OrderSide
from app.paper_trading.errors import NoPriceAvailableError
from app.repositories.candles import CandleRepository
from app.services.candle_ingest import resolution_duration
from app.state.manager import MarketStateManager

#: A simple fixed-basis-point model — see this module's own docstring for
#: why, and for what a more realistic (order-book-aware) model would need.
PAPER_TRADING_SLIPPAGE_BPS_DEFAULT = 5
PAPER_TRADING_FEE_BPS_DEFAULT = 10

_BPS_DIVISOR = Decimal(10_000)


def is_stale(observed_at: datetime, threshold: timedelta) -> bool:
    now = datetime.now(UTC)
    observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    return (now - observed) > threshold


async def resolve_current_price(
    *,
    state_manager: MarketStateManager,
    candle_repository: CandleRepository,
    market_id: uuid.UUID,
    symbol: str,
    staleness_threshold: timedelta,
) -> FillQuote:
    """Resolve the real price a market order for `symbol` would fill against.

    Ticker `last_price`, then trade `price` (the same precedence
    `MarketStateManager.snapshot()` already uses for its own metrics
    view), then the latest stored candle's own close at the finest
    timeframe actually stored for this market — never interpolated,
    never a second, hypothetical price invented for the occasion.
    Raises `NoPriceAvailableError` only when none of the three exist at
    all for this symbol.
    """
    ticker = state_manager.get_latest_ticker(symbol)
    if ticker is not None and ticker.last_price is not None:
        return FillQuote(
            price=ticker.last_price,
            source="ticker",
            observed_at=ticker.event_time,
            is_stale=is_stale(ticker.event_time, staleness_threshold),
        )

    trade = state_manager.get_latest_trade(symbol)
    if trade is not None:
        return FillQuote(
            price=trade.price,
            source="trade",
            observed_at=trade.event_time,
            is_stale=is_stale(trade.event_time, staleness_threshold),
        )

    timeframes = await candle_repository.get_available_timeframes(market_id)
    if not timeframes:
        raise NoPriceAvailableError(symbol)
    finest_timeframe = min(timeframes, key=resolution_duration)
    candle = await candle_repository.get_latest_candle(market_id, finest_timeframe)
    if candle is None:
        raise NoPriceAvailableError(symbol)
    return FillQuote(
        price=candle.close,
        source="candle_close",
        observed_at=candle.open_time,
        is_stale=is_stale(candle.open_time, staleness_threshold),
    )


def apply_fill_model(
    quote: FillQuote,
    *,
    side: OrderSide,
    quantity: Decimal,
    slippage_bps: int,
    fee_bps: int,
) -> FillResult:
    """Apply the modeled slippage and fee to a resolved quote.

    Slippage always moves the fill *against* the trader: a buy fills
    higher than the quote, a sell fills lower — never in the trader's
    favor, since that would be exactly the unrealistically generous fill
    this feature exists to avoid. The fee is charged on the fill's own
    notional (`fill_price * quantity`), always a cost.
    """
    slippage_fraction = Decimal(slippage_bps) / _BPS_DIVISOR
    if side == "buy":
        fill_price = quote.price * (Decimal(1) + slippage_fraction)
    else:
        fill_price = quote.price * (Decimal(1) - slippage_fraction)
    slippage_applied = abs(fill_price - quote.price)

    notional = fill_price * quantity
    fee_applied = notional * Decimal(fee_bps) / _BPS_DIVISOR

    return FillResult(
        quote=quote,
        fill_price=fill_price,
        slippage_applied=slippage_applied,
        fee_applied=fee_applied,
        notional=notional,
    )
