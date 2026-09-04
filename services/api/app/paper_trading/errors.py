"""Domain errors for Paper Trading.

An unknown market symbol (`app.services.market_query.MarketNotFoundError`)
is reused verbatim, not duplicated here — only what's genuinely new to
placing a simulated order is defined below.
"""

from fastapi import status

from app.core.exceptions import AppError


class PaperAccountNotFoundError(AppError):
    """Raised when the requested paper trading account id does not exist."""

    def __init__(self, account_id: object) -> None:
        super().__init__(
            f"Paper trading account {account_id} not found",
            code="paper_account_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InsufficientBalanceError(AppError):
    """Raised when a buy order would take the account's cash balance negative.

    Rejected outright — this account never goes negative and never uses
    margin (this feature's own spec: no margin, no leverage).
    """

    def __init__(self, required: object, available: object) -> None:
        super().__init__(
            f"Order requires {required} (notional + fee) but the account only has "
            f"{available} available — this account has no margin, so the order is rejected "
            "rather than partially filled or allowed to go negative",
            code="insufficient_balance",
        )


class InsufficientPositionError(AppError):
    """Raised when a sell would exceed the account's currently-held quantity.

    Long-only (this feature's own spec: no shorting) — a sell can only
    reduce or close an existing long position, never open a negative one.
    """

    def __init__(self, symbol: str, requested: object, held: object) -> None:
        super().__init__(
            f"Cannot sell {requested} of {symbol!r}: this account holds only {held} — "
            "this platform is long-only, so a sell can never exceed the held quantity "
            "(no shorting)",
            code="insufficient_position",
        )


class TradingHaltedError(AppError):
    """Raised when an order is attempted against an account whose trading
    has been halted by the drawdown limit.

    Does not self-heal on balance recovery (this feature's own spec) — an
    explicit `POST .../resume-trading` is required before any new order
    can be placed, no matter how the balance moves afterward.
    """

    def __init__(self, balance: object, peak_balance: object, max_drawdown_pct: object) -> None:
        super().__init__(
            f"Trading is halted for this account: balance {balance} has fallen more than "
            f"{max_drawdown_pct}% below its peak of {peak_balance}. Resume trading explicitly "
            "before placing another order — a halt never clears itself on balance recovery.",
            code="trading_halted",
        )


class MaxPositionSizeExceededError(AppError):
    """Raised when a single order's resulting position value would exceed
    the account's `max_position_size_pct` of its current balance.

    Computed against the *current* price and *current* balance, never the
    price a position was originally opened at (this feature's own spec) —
    a stale-priced check would be exactly the kind of dishonest simulation
    this platform's realistic-execution guarantee exists to avoid.
    """

    def __init__(
        self,
        symbol: str,
        resulting_value: object,
        balance: object,
        resulting_pct: object,
        max_pct: object,
    ) -> None:
        super().__init__(
            f"This order would bring the {symbol!r} position to a value of {resulting_value} — "
            f"{resulting_pct}% of the current balance of {balance} — exceeding the "
            f"{max_pct}% max position size limit for this account",
            code="max_position_size_exceeded",
        )


class MaxExposureExceededError(AppError):
    """Raised when total open-position value (every symbol, at current
    prices) after this order would exceed the account's `max_exposure_pct`
    of its current balance.

    Computed against every open position's *current* price, not each
    position's own entry price — the same live-price-with-fallback lookup
    (`app/paper_trading/pricing.py`) every other read of this account's
    positions already uses.
    """

    def __init__(
        self, resulting_exposure: object, balance: object, resulting_pct: object, max_pct: object
    ) -> None:
        super().__init__(
            f"This order would bring total exposure to {resulting_exposure} — {resulting_pct}% "
            f"of the current balance of {balance} — exceeding the {max_pct}% max exposure limit "
            "for this account",
            code="max_exposure_exceeded",
        )


class AccountUpdateConflictError(AppError):
    """Raised only if the optimistic-concurrency guard around placing an
    order (`PaperAccountRepository.try_apply_trade_effects`) loses every
    one of its bounded retries — i.e. this account had another order (or a
    resume-trading call) commit against it on *every single* attempt this
    request made. Practically never hit by two concurrent requests (one
    retry is enough), but a request is never left to loop forever.
    """

    def __init__(self, attempts: int) -> None:
        super().__init__(
            f"Could not place this order after {attempts} attempts — this account changed "
            "concurrently on every attempt. Please retry.",
            code="account_update_conflict",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidPaperOrderSortError(AppError):
    """Raised when an order-history list request names an unsupported sort column."""

    def __init__(self, sort: str, direction: str, available: tuple[str, ...]) -> None:
        super().__init__(
            f"Invalid sort {sort!r}/{direction!r}. Available sort columns: "
            f"{', '.join(available)}; direction must be 'asc' or 'desc'",
            code="invalid_paper_order_sort",
        )


class NoPriceAvailableError(AppError):
    """Raised when no live ticker/trade and no stored candle exist at all
    for the requested symbol — there is genuinely nothing to fill against."""

    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"No price available for {symbol!r} — no live ticker/trade is flowing and no "
            "candle has ever been stored for it",
            code="no_price_available",
            status_code=status.HTTP_404_NOT_FOUND,
        )
