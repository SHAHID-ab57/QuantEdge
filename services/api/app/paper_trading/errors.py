"""Domain errors for Paper Trading.

An unknown market symbol (`app.services.market_query.MarketNotFoundError`)
is reused verbatim, not duplicated here — only what's genuinely new to
placing a simulated order is defined below. The automated strategy's own
config errors reuse `app.training.errors.TrainingJobNotFoundError` the
same way, for an unknown `strategy_training_job_id` — only the two
checks genuinely new to *this* feature (a strategy enabled with no job
named at all, and a job with no recorded symbol to trade) get their own
types here.
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
    """Raised when opening or adding to a position would take the account's
    available cash negative.

    The cash an order needs is the margin it posts (the whole notional at 1x
    leverage) plus its fee. Rejected outright — this account's cash never
    goes negative, and an order is never partially filled.
    """

    def __init__(self, required: object, available: object) -> None:
        super().__init__(
            f"Order requires {required} (margin + fee; the whole notional at 1x leverage) but "
            f"the account only has {available} available cash, so the order is rejected "
            "rather than partially filled or allowed to go negative",
            code="insufficient_balance",
        )


class InsufficientPositionError(AppError):
    """Raised when an order would reduce a position by more than it holds
    (including selling with no position at all, for an automated caller,
    which is long-only).

    Also the base of `PositionFlipError`, the manual-order version of
    "larger than the position it reduces".
    """

    def __init__(self, symbol: str, requested: object, held: object) -> None:
        super().__init__(
            f"Cannot reduce {symbol!r} by {requested}: this account holds only {held}",
            code="insufficient_position",
        )


class PositionFlipError(InsufficientPositionError):
    """An order larger than the held position, on the opposite side, would
    close it and open the reverse position in one step. Rejected (the
    conservative choice: Delta's behaviour here is undocumented): send a
    reduce-to-zero order and a separate opening order instead."""

    def __init__(self, symbol: str, requested: object, held: object) -> None:
        super().__init__(symbol, requested, held)
        self.message = (
            f"Cannot reduce {symbol!r} by {requested}: this account holds only {held}. An order "
            "can never carry a position through zero into the opposite side in one step — "
            "close it first, then open the other side with a separate order"
        )
        self.args = (self.message,)
        # Same `code` as any over-reduce always had: a plain long that is
        # over-sold is the same rejection it always was to an API client.


class ReduceOnlyViolationError(AppError):
    """A reduce-only order that would open or increase a position."""

    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"This reduce-only order would open or increase the {symbol!r} position, not reduce it",
            code="reduce_only_violation",
        )


class LeverageLimitExceededError(AppError):
    """Requested leverage is above this account's `max_leverage`."""

    def __init__(self, requested: object, maximum: object) -> None:
        super().__init__(
            f"Leverage {requested}x exceeds this account's maximum of {maximum}x",
            code="leverage_limit_exceeded",
        )


class LeverageMismatchError(AppError):
    """An order to add to an open position named a different leverage than
    the position was opened with (leverage is fixed when a position opens)."""

    def __init__(self, symbol: str, requested: object, position_leverage: object) -> None:
        super().__init__(
            f"The {symbol!r} position was opened at {position_leverage}x and leverage is fixed "
            f"for its lifetime; this order asked for {requested}x. Omit leverage to add to it, "
            "or close the position first.",
            code="leverage_mismatch",
        )


class LeverageNotionalLimitError(AppError):
    """A short or leveraged position larger than the size at which Delta's
    margin requirements start to scale (not modelled, so rejected rather than
    approximated)."""

    def __init__(self, resulting_notional: object, maximum: object) -> None:
        super().__init__(
            f"A short or leveraged position of notional {resulting_notional} exceeds "
            f"{maximum}, the size beyond which Delta's margin requirements scale up (not "
            "modelled here); reduce the size",
            code="leverage_notional_limit_exceeded",
        )


class AutomatedOrderRestrictedError(AppError):
    """The automated strategy asked for something other than an unleveraged
    long. Shorts and leverage are for manually placed orders only."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Automated orders are limited to unleveraged (1x) long positions: {detail}",
            code="automated_order_restricted",
        )


class StopBeyondLiquidationError(AppError):
    """A stop-loss placed beyond the position's liquidation price could never
    fire: the exchange would liquidate the position first."""

    def __init__(self, stop_loss_price: object, liquidation_price: object, side: str) -> None:
        direction = "above" if side == "long" else "below"
        super().__init__(
            f"stop_loss_price {stop_loss_price} for a {side} position must be {direction} its "
            f"liquidation price {liquidation_price}; a stop beyond it can never trigger, "
            "because the position is liquidated first",
            code="stop_beyond_liquidation",
        )


class TradingHaltedError(AppError):
    """Raised when an order that would open or add to a position is
    attempted against an account whose trading has been halted by the
    drawdown limit (measured on equity).

    The halt blocks *new risk* only: reduce-only orders and triggered exits
    still go through, and a liquidation is never blockable. It does not
    self-heal on recovery (this feature's own spec) — an explicit
    `POST .../resume-trading` is required before new risk can be taken,
    no matter how equity moves afterward.
    """

    def __init__(self, equity: object, peak_balance: object, max_drawdown_pct: object) -> None:
        super().__init__(
            f"Trading is halted for this account: equity {equity} has fallen more than "
            f"{max_drawdown_pct}% below its peak of {peak_balance}. Only orders that reduce an "
            "existing position are accepted while halted. Resume trading explicitly before "
            "opening or adding to a position — a halt never clears itself on recovery.",
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


class InvalidStopLossPriceError(AppError):
    """Raised when a stop-loss price would not sit below the current
    price for a long position — it would trigger the instant it's set,
    which is never a real stop.
    """

    def __init__(self, stop_loss_price: object, current_price: object, side: str = "long") -> None:
        relation, wrong = ("below", "at or above") if side == "long" else ("above", "at or below")
        super().__init__(
            f"stop_loss_price {stop_loss_price} must be {relation} the current price "
            f"{current_price} for a {side} position — a value {wrong} the current price "
            "would trigger immediately",
            code="invalid_stop_loss_price",
        )


class InvalidTakeProfitPriceError(AppError):
    """Raised when a take-profit price would not sit above the current
    price for a long position — it would trigger the instant it's set.
    """

    def __init__(
        self, take_profit_price: object, current_price: object, side: str = "long"
    ) -> None:
        relation, wrong = ("above", "at or below") if side == "long" else ("below", "at or above")
        super().__init__(
            f"take_profit_price {take_profit_price} must be {relation} the current price "
            f"{current_price} for a {side} position — a value {wrong} the current price "
            "would trigger immediately",
            code="invalid_take_profit_price",
        )


class StopLossNotBelowTakeProfitError(AppError):
    """Raised when a stop-loss and take-profit would be set together such
    that the stop-loss is not strictly below the take-profit.

    Each is independently validated against *its own* current price at
    the moment it's set (`InvalidStopLossPriceError`/
    `InvalidTakeProfitPriceError`), but that alone doesn't prevent
    setting a high stop-loss and a low take-profit at two *different*
    times as the price moves — this closes that gap so the two trigger
    conditions (`price <= stop_loss_price`, `price >= take_profit_price`)
    can never both be true for the same price, ever, rather than leaving
    a single tick able to satisfy both at once (see
    `app.paper_trading.monitor`'s own docstring for the full reasoning).
    """

    def __init__(
        self, stop_loss_price: object, take_profit_price: object, side: str = "long"
    ) -> None:
        relation = "below" if side == "long" else "above"
        super().__init__(
            f"stop_loss_price {stop_loss_price} must be strictly {relation} take_profit_price "
            f"{take_profit_price} for a {side} position — otherwise a single price could "
            "satisfy both trigger conditions at once",
            code="stop_loss_not_below_take_profit",
        )


class PositionNotFoundError(AppError):
    """Raised when the requested account holds no open position in this symbol."""

    def __init__(self, account_id: object, symbol: str) -> None:
        super().__init__(
            f"Account {account_id} holds no open position in {symbol!r}",
            code="position_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidPaperOrderSortError(AppError):
    """Raised when an order-history list request names an unsupported sort column."""

    def __init__(self, sort: str, direction: str, available: tuple[str, ...]) -> None:
        super().__init__(
            f"Invalid sort {sort!r}/{direction!r}. Available sort columns: "
            f"{', '.join(available)}; direction must be 'asc' or 'desc'",
            code="invalid_paper_order_sort",
        )


class StrategyMissingTrainingJobError(AppError):
    """Raised when a strategy update would leave `strategy_enabled=True`
    with no `strategy_training_job_id` at all — the strategy has nothing
    to request a prediction from and can never legitimately be "on" in
    that state.
    """

    def __init__(self) -> None:
        super().__init__(
            "strategy_enabled cannot be set without a strategy_training_job_id — the "
            "automated strategy needs a completed training job to request predictions from",
            code="strategy_missing_training_job",
        )


class StrategyTrainingJobMissingSymbolError(AppError):
    """Raised when the named training job has no recorded `symbol` —
    i.e. it was never trained on real market data (`requires_real_data`
    is false for its adapter, or it predates that job ever running), so
    there is no market for the strategy to request a prediction for, let
    alone trade.
    """

    def __init__(self, training_job_id: object) -> None:
        super().__init__(
            f"Training job {training_job_id} has no recorded symbol — it was not trained on "
            "real market data, so the automated strategy has no market to predict for",
            code="strategy_training_job_missing_symbol",
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


class ThresholdsOnReducingOrderError(AppError):
    """A stop-loss/take-profit was named on an order that reduces a position."""

    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"stop_loss_price/take_profit_price only apply to an order that opens or adds to "
            f"a position; this order reduces the {symbol!r} position, which has nothing left "
            "to protect. Set thresholds with PATCH .../positions/{symbol} instead.",
            code="thresholds_on_reducing_order",
        )
