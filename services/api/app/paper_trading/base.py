"""Pure dataclasses for one paper-trading fill: the resolved quote, and
the slippage/fee-adjusted result computed from it.

Framework-light and database-free, mirroring `app/backtest/base.py`'s own
posture: nothing here touches SQLAlchemy or knows what a `PaperAccount`/
`PaperOrder`/`PaperPosition` ORM row is — `app/services/paper_trading.py`
is the one place a database session exists, and maps these onto real rows.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

PriceSource = Literal["ticker", "trade", "candle_close"]
OrderSide = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class FillQuote:
    """The real price a market order would fill against, resolved *before*
    slippage — and which real data it came from.

    `observed_at` is the quote's own timestamp (a live ticker/trade's
    `event_time`, or a fallback candle's own `open_time`) — never "now";
    `is_stale` is `observed_at` compared against the configured staleness
    threshold, computed once here so every caller sees the identical
    verdict rather than each re-deriving its own age check.
    """

    price: Decimal
    source: PriceSource
    observed_at: datetime
    is_stale: bool


@dataclass(frozen=True, slots=True)
class FillResult:
    """One market order's full, realistic execution outcome — the
    paper-trading equivalent of a real exchange fill confirmation.

    `raw_price` (the quote, before slippage) and `fill_price` (what the
    account was actually charged/credited) are both kept, always, so
    `slippage_applied` is never a hidden adjustment folded silently into
    one opaque number.
    """

    quote: FillQuote
    fill_price: Decimal
    slippage_applied: Decimal
    fee_applied: Decimal
    notional: Decimal
