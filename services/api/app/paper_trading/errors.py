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
