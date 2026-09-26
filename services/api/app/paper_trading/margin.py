"""Isolated-margin arithmetic for paper trading: liquidation/bankruptcy
prices, unrealized PnL, position equity, and funding payments.

Pure and database-free, like `app/paper_trading/pricing.py`: nothing here
touches SQLAlchemy or an ORM row. `app/services/paper_trading.py` is the one
place that maps these numbers onto accounts and positions.

**Contract model.** Delta Exchange India's ETHUSD/BTCUSD perpetuals are
*linear* (USD-margined, `notional_type: vanilla`): a position's value is
`price * quantity` in USD, and its profit/loss is `(price - entry) *
quantity` for a long and `(entry - price) * quantity` for a short. Margin is
posted, and profit/loss settles, in USD. (The docs' worked liquidation
examples are for an *inverse* contract, which is a different formula, see
below.)

**Liquidation, stated from Delta's own definition.** Delta defines the
liquidation price as the mark price at which "the difference of Position
Margin minus Unrealized PnL of the position is equal to the Maintenance
Margin" (Isolated Margin Liquidation page), and the bankruptcy price as the
price at which the unrealized loss equals the position margin. Writing `m`
for the position margin, `q` the quantity, `E` the average entry price, `P`
the mark price and `mm` the maintenance-margin rate, and taking the
maintenance margin as `mm * P * q` (a fraction of the position's value at the
liquidation price):

- long:  `m - (E - P) * q = mm * P * q`  ->  `P = (E*q - m) / (q * (1 - mm))`
- short: `m - (P - E) * q = mm * P * q`  ->  `P = (E*q + m) / (q * (1 + mm))`

With `m = E*q / leverage` these reduce to the closed forms in
`docs/research/FUTURES_MECHANICS_AND_LEVERAGE_DESIGN.md` section 1.3.

**Verification status (read this before trusting these numbers).** These
formulas are *derived from Delta's documented condition*; they are **not**
confirmed against a linear-contract liquidation price from Delta itself.
Delta's only published worked examples are for an inverse contract (checked
in `tests/paper_trading/test_margin.py::TestDeltaDocumentedExamples`, where
the inverse form matches them and the linear form does not), so they cannot
confirm the linear one. There is one further genuine ambiguity: which price
the maintenance margin is taken on (the liquidation price, used here, or the
entry price). The two differ by at most `mm * (1 - IM)` of entry (about
0.25% of entry at 1x, and under 0.03% at 10x and above). Closing this gap
needs one reading from Delta's liquidation-price calculator; the whole
choice lives in `liquidation_price` below, so a verified figure changes
this one function and the reference table in the tests.
"""

from decimal import Decimal
from typing import Literal

PositionSide = Literal["long", "short"]

_ZERO = Decimal(0)
_ONE = Decimal(1)


def initial_margin(*, notional: Decimal, leverage: Decimal) -> Decimal:
    """Margin posted to open `notional` at `leverage`: `notional / leverage`."""
    return notional / leverage


def unrealized_pnl(
    *, side: PositionSide, entry_price: Decimal, price: Decimal, quantity: Decimal
) -> Decimal:
    """Mark-to-market profit/loss at `price`, with no slippage or fee applied."""
    if side == "long":
        return (price - entry_price) * quantity
    return (entry_price - price) * quantity


def position_equity(
    *,
    side: PositionSide,
    entry_price: Decimal,
    price: Decimal,
    quantity: Decimal,
    margin: Decimal,
) -> Decimal:
    """What an open position is worth to the account right now: its posted
    margin plus its unrealized PnL. For a 1x long this is exactly
    `quantity * price`, the value the engine has always used for one."""
    return margin + unrealized_pnl(
        side=side, entry_price=entry_price, price=price, quantity=quantity
    )


def liquidation_price(
    *,
    side: PositionSide,
    entry_price: Decimal,
    quantity: Decimal,
    margin: Decimal,
    maintenance_margin_rate: Decimal,
) -> Decimal | None:
    """The mark price at which this isolated position is liquidated, or
    `None` if it cannot be (a long whose posted margin covers its whole
    notional, i.e. an unleveraged long, can only reach zero).

    See the module docstring for the derivation and, importantly, for what
    has and has not been verified about it.
    """
    if quantity <= 0:
        return None
    notional = entry_price * quantity
    if side == "long":
        price = (notional - margin) / (quantity * (_ONE - maintenance_margin_rate))
        return price if price > 0 else None
    return (notional + margin) / (quantity * (_ONE + maintenance_margin_rate))


def liquidation_distance_fraction(
    *, side: PositionSide, leverage: Decimal, maintenance_margin_rate: Decimal
) -> Decimal | None:
    """How far, as a fraction of the entry price, the mark price must move
    against a position opened at `leverage` before it is liquidated (`None`
    when it cannot be: an unleveraged long). Independent of the entry price, so
    it is what a percentage stop-loss must be compared against."""
    entry = Decimal(1)
    price = liquidation_price(
        side=side,
        entry_price=entry,
        quantity=Decimal(1),
        margin=initial_margin(notional=entry, leverage=leverage),
        maintenance_margin_rate=maintenance_margin_rate,
    )
    if price is None:
        return None
    return abs(entry - price)


def bankruptcy_price(
    *, side: PositionSide, entry_price: Decimal, quantity: Decimal, margin: Decimal
) -> Decimal | None:
    """The price at which the unrealized loss equals the posted margin (the
    position is worth nothing). `None` for a long that cannot reach it."""
    if quantity <= 0:
        return None
    if side == "long":
        price = entry_price - margin / quantity
        return price if price > 0 else None
    return entry_price + margin / quantity


def is_liquidated(*, side: PositionSide, mark_price: Decimal, liquidation: Decimal | None) -> bool:
    """Whether `mark_price` has reached the liquidation price (`<=` for a
    long, `>=` for a short). Never `==`: a gap past the level still counts."""
    if liquidation is None:
        return False
    if side == "long":
        return mark_price <= liquidation
    return mark_price >= liquidation


def gapped_through_bankruptcy(
    *, side: PositionSide, mark_price: Decimal, bankruptcy: Decimal | None
) -> bool:
    """Whether the mark price has already moved past the price at which the
    position's whole margin was lost, so the real loss would exceed what was
    posted. Isolated margin caps the paper account's loss at the margin; this
    flag records that the venue would have absorbed the difference."""
    if bankruptcy is None:
        return False
    if side == "long":
        return mark_price < bankruptcy
    return mark_price > bankruptcy


def effective_leverage(*, notional: Decimal, equity: Decimal) -> Decimal:
    """Total open notional over account equity (0 when there is none)."""
    if equity <= 0:
        return _ZERO
    return notional / equity


def funding_payment(
    *,
    side: PositionSide,
    quantity: Decimal,
    index_price: Decimal,
    funding_rate: Decimal,
) -> Decimal:
    """What this position *pays* at one funding time (negative = receives).

    `funding_rate` is a **fraction** per interval (0.0001 = 0.01%), never
    Delta's published percent figure: that conversion happens once, at
    ingestion (`app.services.funding_rates.funding_percent_to_fraction`).
    Per Delta, the payment is `position value at the index price *
    funding rate`; when the rate is positive longs pay shorts, and when it is
    negative shorts pay longs.
    """
    position_value = quantity * index_price
    payment = position_value * funding_rate
    return payment if side == "long" else -payment
