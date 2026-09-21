"""Isolated-margin short and leveraged positions for manually placed paper
orders (M3-E5-T2): fills, PnL and cash/margin accounting that mirror the long
side's discipline, order semantics, and every pre-trade risk limit re-derived
on equity and notional.

All expected numbers are worked out by hand from the modeled costs
(`SLIPPAGE_BPS=5`, `FEE_BPS=10`), never read back from the code under test.
Manual orders pass a `user_id`; the automated strategy's orders are declared
`automated=True` (see `TestAutomatedCaller`).
"""

import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.events.bus import EventBus
from app.paper_trading.errors import (
    AutomatedOrderRestrictedError,
    InsufficientBalanceError,
    InsufficientPositionError,
    InvalidStopLossPriceError,
    InvalidTakeProfitPriceError,
    LeverageLimitExceededError,
    LeverageMismatchError,
    LeverageNotionalLimitError,
    MaxExposureExceededError,
    MaxPositionSizeExceededError,
    PositionFlipError,
    ReduceOnlyViolationError,
    StopBeyondLiquidationError,
    StopLossNotBelowTakeProfitError,
    StrategyLeverageExceedsMaximumError,
    StrategyStopBeyondLiquidationError,
    TradingHaltedError,
)
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperOrderRequest,
    PaperOrderResponse,
    PaperStrategyConfigUpdateRequest,
    PositionThresholdsUpdateRequest,
)
from app.services.paper_trading import PaperTradingService
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory
from tests.paper_trading.test_service import (
    GENEROUS_MAX_PCT,
    build_service,
    publish_ticker,
    seed_market,
)

D = Decimal
MM = D("0.0025")
STRATEGY_MODULE = Path(__file__).parents[2] / "app" / "services" / "paper_trading_strategy.py"


class Env:
    """One market, one account, a live bus, and a manual-order helper."""

    def __init__(
        self,
        service: PaperTradingService,
        bus: EventBus,
        symbol: str,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        self.service = service
        self.bus = bus
        self.symbol = symbol
        self.account_id = account_id
        self.user_id = user_id

    async def order(self, side: str, quantity: str, **extra: object) -> PaperOrderResponse:
        return await self.service.place_order(
            self.account_id,
            PaperOrderRequest(
                symbol=extra.pop("symbol", self.symbol),  # type: ignore[arg-type]
                side=side,  # type: ignore[arg-type]
                quantity=D(quantity),
                **extra,  # type: ignore[arg-type]
            ),
            user_id=self.user_id,
        )

    async def automated(self, side: str, quantity: str, **extra: object) -> PaperOrderResponse:
        """The same order, but as the automated strategy places it: no user, and
        declared `automated=True`."""
        return await self.service.place_order(
            self.account_id,
            PaperOrderRequest(
                symbol=extra.pop("symbol", self.symbol),  # type: ignore[arg-type]
                side=side,  # type: ignore[arg-type]
                quantity=D(quantity),
                **extra,  # type: ignore[arg-type]
            ),
            automated=True,
        )

    async def price(self, value: str, symbol: str | None = None) -> None:
        await publish_ticker(self.bus, symbol or self.symbol, value)

    async def position(self):  # noqa: ANN201
        positions = (await self.service.list_positions(self.account_id)).positions
        return next((p for p in positions if p.symbol == self.symbol), None)

    async def account(self):  # noqa: ANN201
        # Another session (a scheduler, a second service) may have committed
        # since this one last read: never serve a cached row.
        self.service.account_repository.session.expire_all()
        return await self.service.get_account(self.account_id)


async def make_env(
    session_factory: SessionFactory,
    symbol: str,
    *,
    price: str = "2000",
    starting_balance: str = "100000",
    max_leverage: str | None = None,
    max_position: Decimal = GENEROUS_MAX_PCT,
    max_exposure: Decimal = GENEROUS_MAX_PCT,
    max_drawdown: Decimal = GENEROUS_MAX_PCT,
) -> Env:
    await seed_market(session_factory, symbol=symbol)
    bus = EventBus()
    state_manager = MarketStateManager().attach(bus)
    await publish_ticker(bus, symbol, price)
    service = await build_service(session_factory, state_manager)
    account = await service.create_account(
        PaperAccountCreateRequest(
            starting_balance=D(starting_balance),
            max_position_size_pct=max_position,
            max_exposure_pct=max_exposure,
            max_drawdown_pct=max_drawdown,
            max_leverage=D(max_leverage) if max_leverage is not None else None,
        )
    )
    return Env(service, bus, symbol, uuid.UUID(account.id), service._default_user_id)  # noqa: SLF001


def approx(value: object, expected: float, rel: float = 1e-9) -> object:
    return pytest.approx(expected, rel=rel) == float(value)  # type: ignore[arg-type]


def num(value: object) -> float:
    return float(value)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestShortFillsAndPnl:
    async def test_opening_a_short_fills_below_the_quote_and_posts_margin(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTOPENUSD")
        order = await env.order("sell", "2")

        # A sell fills *against* the trader: lower than the $2000 quote by 5 bps.
        assert num(order.fill_price) == pytest.approx(1999.0)
        assert num(order.slippage_applied) == pytest.approx(1.0)
        assert num(order.notional) == pytest.approx(3998.0)
        assert num(order.fee_applied) == pytest.approx(3.998)  # 10 bps of the notional
        assert order.side == "sell"
        assert order.position_side == "short"
        assert num(order.leverage) == 1
        assert num(order.margin_applied) == pytest.approx(3998.0)  # 1x: the whole notional
        assert order.realized_pnl is None  # opening realizes nothing but its fee

        position = await env.position()
        assert position is not None
        assert position.side == "short"
        assert num(position.quantity) == 2
        assert num(position.average_entry_price) == pytest.approx(1999.0)
        assert num(position.margin) == pytest.approx(3998.0)

        account = await env.account()
        assert num(account.balance) == pytest.approx(100000 - 3998.0 - 3.998)
        assert num(account.realized_pnl) == pytest.approx(-3.998)

    async def test_covering_a_short_at_a_lower_price_realizes_a_gain(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTWINUSD")
        await env.order("sell", "2")
        await env.price("1900")
        cover = await env.order("buy", "2")

        # A buy fills *against* the trader: higher than the $1900 quote by 5 bps.
        assert num(cover.fill_price) == pytest.approx(1900.95)
        assert num(cover.fee_applied) == pytest.approx(3.8019)
        # (1999 - 1900.95) * 2 - fee
        assert cover.realized_pnl is not None
        assert num(cover.realized_pnl) == pytest.approx(196.1 - 3.8019)
        assert cover.position_side == "short"

        assert await env.position() is None
        account = await env.account()
        assert num(account.realized_pnl) == pytest.approx(-3.998 + 196.1 - 3.8019)
        # Flat, so cash reconciles exactly against starting balance + realized PnL.
        assert num(account.balance) == pytest.approx(100000 + num(account.realized_pnl))

    async def test_covering_a_short_at_a_higher_price_realizes_a_loss(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTLOSSUSD")
        await env.order("sell", "2")
        await env.price("2100")
        cover = await env.order("buy", "2")

        # fill 2100 * 1.0005 = 2101.05; (1999 - 2101.05) * 2 = -204.1; fee 4.2021
        assert cover.realized_pnl is not None
        assert num(cover.realized_pnl) == pytest.approx(-204.1 - 4.2021)
        account = await env.account()
        assert num(account.balance) == pytest.approx(100000 + num(account.realized_pnl))
        assert num(account.balance) < 100000

    async def test_a_shorts_unrealized_pnl_is_marked_to_the_live_price(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTMARKUSD")
        await env.order("sell", "2")
        await env.price("1950")
        position = await env.position()
        assert position is not None
        assert num(position.unrealized_pnl) == pytest.approx((1999.0 - 1950.0) * 2)
        await env.price("2050")
        position = await env.position()
        assert position is not None
        assert num(position.unrealized_pnl) == pytest.approx((1999.0 - 2050.0) * 2)

    async def test_adding_to_a_short_vwap_averages_the_entry_and_adds_margin(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTADDUSD")
        await env.order("sell", "2")  # fill 1999
        await env.price("2200")
        await env.order("sell", "2")  # fill 2200 * 0.9995 = 2198.9
        position = await env.position()
        assert position is not None
        assert num(position.quantity) == 4
        assert num(position.average_entry_price) == pytest.approx((1999 * 2 + 2198.9 * 2) / 4)
        assert num(position.margin) == pytest.approx(1999 * 2 + 2198.9 * 2)

    async def test_a_partial_cover_releases_margin_pro_rata_and_keeps_the_liquidation_price(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTPARTUSD", max_leverage="5")
        await env.order("sell", "4", leverage="5")
        before = await env.position()
        assert before is not None
        cover = await env.order("buy", "1")
        after = await env.position()
        assert after is not None
        assert num(after.quantity) == 3
        assert num(cover.margin_applied) == pytest.approx(num(before.margin) / 4)
        assert num(after.margin) == pytest.approx(num(before.margin) * 3 / 4)
        assert after.liquidation_price is not None and before.liquidation_price is not None
        assert num(after.liquidation_price) == pytest.approx(num(before.liquidation_price))


@pytest.mark.asyncio
class TestLeveragedMargin:
    async def test_opening_at_leverage_posts_notional_over_leverage_from_cash(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTLEVOPENUSD", max_leverage="10")
        order = await env.order("buy", "5", leverage="5")

        # buy fills at 2000 * 1.0005 = 2001; notional 10005; margin 10005 / 5 = 2001
        assert num(order.fill_price) == pytest.approx(2001.0)
        assert num(order.notional) == pytest.approx(10005.0)
        assert num(order.margin_applied) == pytest.approx(2001.0)
        assert num(order.fee_applied) == pytest.approx(10.005)  # on the full notional
        account = await env.account()
        assert num(account.balance) == pytest.approx(100000 - 2001.0 - 10.005)

        position = await env.position()
        assert position is not None
        assert num(position.leverage) == 5
        assert num(position.margin) == pytest.approx(2001.0)
        # liquidation = E(1-IM)/(1-MM) with IM = 20%: 2001 * 0.8 / 0.9975
        assert position.liquidation_price is not None
        assert num(position.liquidation_price) == pytest.approx(2001 * 0.8 / 0.9975)
        # 4.5 x 5 = distance shown to the user
        assert position.liquidation_distance_pct is not None
        assert num(position.liquidation_distance_pct) == pytest.approx(
            (2000 - 2001 * 0.8 / 0.9975) / 2000 * 100
        )

    async def test_a_leveraged_long_closes_with_price_pnl_on_the_full_notional(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTLEVCLOSEUSD", max_leverage="10")
        await env.order("buy", "5", leverage="5")
        await env.price("2100")
        close = await env.order("sell", "5")

        # sell fills 2100 * 0.9995 = 2098.95; gross (2098.95 - 2001) * 5 = 489.75; fee 10.49475
        assert close.realized_pnl is not None
        assert num(close.realized_pnl) == pytest.approx(489.75 - 10.49475)
        assert num(close.margin_applied) == pytest.approx(2001.0)  # released
        account = await env.account()
        assert num(account.realized_pnl) == pytest.approx(-10.005 + 489.75 - 10.49475)
        assert num(account.balance) == pytest.approx(100000 + num(account.realized_pnl))

    async def test_a_leveraged_position_ties_up_much_less_cash_than_an_unleveraged_one(
        self, session_factory: SessionFactory
    ) -> None:
        one = await make_env(session_factory, "PTLEVCASH1USD", max_leverage="10")
        ten = await make_env(session_factory, "PTLEVCASH10USD", max_leverage="10")
        await one.order("buy", "5")
        await ten.order("buy", "5", leverage="10")
        cash_one = num((await one.account()).balance)
        cash_ten = num((await ten.account()).balance)
        assert cash_ten - cash_one == pytest.approx(10005.0 * (1 - 0.1))

    async def test_an_order_the_cash_cannot_margin_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTLEVBROKEUSD", starting_balance="1000")
        # 1x: needs $2001+ for one unit; the account has $1000.
        with pytest.raises(InsufficientBalanceError):
            await env.order("buy", "1")
        with pytest.raises(InsufficientBalanceError):
            await env.order("sell", "1")
        # ...but 5x needs only ~$160 of margin for a 0.4-unit ($800) position.
        assert (await env.order("buy", "0.4", leverage="5")).leverage == 5

    async def test_leverage_above_the_accounts_maximum_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTLEVCAPUSD", max_leverage="3")
        with pytest.raises(LeverageLimitExceededError):
            await env.order("buy", "1", leverage="5")
        assert await env.position() is None
        await env.order("buy", "1", leverage="3")

    async def test_a_new_accounts_default_max_leverage_is_conservative(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTLEVDEFUSD")
        assert num((await env.account()).max_leverage) == 5

    async def test_leverage_is_fixed_for_the_life_of_a_position(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTLEVFIXUSD", max_leverage="10")
        await env.order("buy", "1", leverage="5")
        with pytest.raises(LeverageMismatchError):
            await env.order("buy", "1", leverage="3")
        # Omitting leverage adds at the position's own; naming the same is fine too.
        await env.order("buy", "1")
        await env.order("buy", "1", leverage="5")
        position = await env.position()
        assert position is not None
        assert num(position.quantity) == 3
        assert num(position.leverage) == 5

    async def test_a_reducing_order_ignores_any_leverage_it_names(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTLEVREDUSD", max_leverage="10")
        await env.order("buy", "2", leverage="5")
        reduce = await env.order("sell", "1", leverage="2")
        assert num(reduce.leverage) == 5  # the position's own, recorded on the order

    async def test_a_short_or_leveraged_position_above_deltas_margin_scaling_size_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        """Margin requirements scale up past Delta's `max_leverage_notional`
        ($100,000); that is not modelled, so it is rejected, not approximated."""
        env = await make_env(session_factory, "PTLEVBIGUSD", starting_balance="10000000")
        with pytest.raises(LeverageNotionalLimitError):
            await env.order("sell", "60")  # 60 x 2000 = $120,000 short
        with pytest.raises(LeverageNotionalLimitError):
            await env.order("buy", "60", leverage="2")
        # An unleveraged long is exactly today's position: not subject to it.
        await env.order("buy", "60")


@pytest.mark.asyncio
class TestOrderSemantics:
    async def test_an_order_that_would_flip_a_position_through_zero_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTFLIPUSD")
        await env.order("buy", "2")
        with pytest.raises(PositionFlipError) as long_flip:
            await env.order("sell", "3")
        assert long_flip.value.code == "insufficient_position"  # unchanged API code
        # It is still an `InsufficientPositionError`, as an over-sell always was.
        assert isinstance(long_flip.value, InsufficientPositionError)

        await env.order("sell", "2")  # close it
        await env.order("sell", "2")  # open a short
        with pytest.raises(PositionFlipError):
            await env.order("buy", "3")

        position = await env.position()
        assert position is not None
        assert position.side == "short"
        assert num(position.quantity) == 2  # the rejected orders changed nothing

    async def test_a_reduce_only_order_that_would_open_or_add_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTREDONLYUSD")
        with pytest.raises(ReduceOnlyViolationError):
            await env.order("sell", "1", reduce_only=True)  # would open a short
        await env.order("buy", "2")
        with pytest.raises(ReduceOnlyViolationError):
            await env.order("buy", "1", reduce_only=True)  # would add to the long
        reduced = await env.order("sell", "1", reduce_only=True)
        assert reduced.reduce_only is True
        position = await env.position()
        assert position is not None
        assert num(position.quantity) == 1

    async def test_closing_a_position_leaves_it_flat_and_a_new_one_starts_fresh(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTREOPENUSD", max_leverage="5")
        await env.order("sell", "2", leverage="5", stop_loss_price="2300")
        await env.order("buy", "2")
        assert await env.position() is None
        await env.order("buy", "1")  # a long this time
        position = await env.position()
        assert position is not None
        assert position.side == "long"
        assert num(position.leverage) == 1
        assert position.stop_loss_price is None  # nothing carried over
        assert position.liquidation_price is None

    async def test_thresholds_can_be_set_on_the_order_that_opens_a_short(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTTHRUSD")
        await env.order("sell", "1", stop_loss_price="2200", take_profit_price="1800")
        position = await env.position()
        assert position is not None
        assert num(position.stop_loss_price or 0) == 2200
        assert num(position.take_profit_price or 0) == 1800


@pytest.mark.asyncio
class TestThresholdsBySide:
    async def test_a_shorts_stop_loss_must_be_above_the_price_and_take_profit_below(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSHORTVALUSD")
        with pytest.raises(InvalidStopLossPriceError) as stop:
            await env.order("sell", "1", stop_loss_price="1900")
        assert "short" in str(stop.value) and "above" in str(stop.value)
        with pytest.raises(InvalidTakeProfitPriceError) as take:
            await env.order("sell", "1", take_profit_price="2100")
        assert "short" in str(take.value) and "below" in str(take.value)
        assert await env.position() is None

    async def test_a_shorts_stop_must_stay_above_its_take_profit(
        self, session_factory: SessionFactory
    ) -> None:
        """Each threshold is valid against the price when set, but the pair
        can't be crossed later as the price moves between the two settings."""
        env = await make_env(session_factory, "PTSHORTCROSSUSD")
        await env.order("sell", "1", take_profit_price="1800")
        await env.price("1500")  # the price falls well past that take-profit
        with pytest.raises(StopLossNotBelowTakeProfitError):
            await env.service.update_position_thresholds(
                env.account_id,
                env.symbol,
                # valid against the $1500 price (above it), but *below* the
                # existing $1800 take-profit: a short's stop must sit above it.
                PositionThresholdsUpdateRequest(stop_loss_price=D("1600")),
                user_id=env.user_id,
            )

    async def test_a_stop_loss_beyond_the_liquidation_price_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        """A 10x long is liquidated ~9.8% below entry; a stop 15% down could
        never fire, because the exchange liquidates first."""
        env = await make_env(session_factory, "PTSTOPLIQLONGUSD", max_leverage="10")
        with pytest.raises(StopBeyondLiquidationError) as error:
            await env.order("buy", "1", leverage="10", stop_loss_price="1700")
        assert error.value.code == "stop_beyond_liquidation"
        # A stop on the safe side of the liquidation price (~1804) is fine.
        await env.order("buy", "1", leverage="10", stop_loss_price="1900")

    async def test_the_same_holds_for_a_short_and_when_updating_thresholds(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSTOPLIQSHORTUSD", max_leverage="10")
        with pytest.raises(StopBeyondLiquidationError):
            await env.order("sell", "1", leverage="10", stop_loss_price="2400")
        await env.order("sell", "1", leverage="10")
        with pytest.raises(StopBeyondLiquidationError):
            await env.service.update_position_thresholds(
                env.account_id,
                env.symbol,
                PositionThresholdsUpdateRequest(stop_loss_price=D("2400")),
                user_id=env.user_id,
            )
        updated = await env.service.update_position_thresholds(
            env.account_id,
            env.symbol,
            PositionThresholdsUpdateRequest(stop_loss_price=D("2100")),
            user_id=env.user_id,
        )
        assert num(updated.stop_loss_price or 0) == 2100

    async def test_adding_that_moves_the_liquidation_price_past_an_existing_stop_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSTOPLIQADDUSD", max_leverage="20")
        # 20x long at ~2001: liquidation ~1906; a stop at 1950 is valid.
        await env.order("buy", "1", leverage="20", stop_loss_price="1950")
        await env.price("1960")
        # Adding at ~1961 lowers the average entry, pulling the liquidation
        # price down, which is *safe*; adding at a HIGHER price pushes it up.
        await env.price("2400")
        with pytest.raises(StopBeyondLiquidationError):
            await env.order("buy", "5", leverage="20")  # avg entry ~2300: liq ~2190 > stop


@pytest.mark.asyncio
class TestRiskLimitsOnEquityAndNotional:
    async def test_the_position_size_limit_is_measured_on_notional_over_equity(
        self, session_factory: SessionFactory
    ) -> None:
        """A 10x position posts a tenth of its notional as margin, but the
        limit is on the *notional* (D7): leverage does not raise the ceiling."""
        env = await make_env(
            session_factory,
            "PTLIMPOSUSD",
            starting_balance="10000",
            max_leverage="10",
            max_position=D("10"),  # $1,000 of notional on $10,000 of equity
        )
        with pytest.raises(MaxPositionSizeExceededError):
            await env.order("buy", "1", leverage="10")  # $2,001 notional, only $200 margin
        await env.order("buy", "0.4", leverage="10")  # $800.4 notional

    async def test_leverage_does_not_raise_the_exposure_ceiling(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(
            session_factory,
            "PTLIMEXPUSD",
            starting_balance="10000",
            max_leverage="10",
            max_exposure=D("50"),  # $5,000 of notional on $10,000 of equity
        )
        # Margin for this is only $1,200 (12% of equity), yet its notional is $6,000.
        with pytest.raises(MaxExposureExceededError):
            await env.order("sell", "3", leverage="5")
        await env.order("sell", "2", leverage="5")  # $3,998 notional: fine

    async def test_the_limits_use_equity_not_the_cash_left_after_posting_margin(
        self, session_factory: SessionFactory
    ) -> None:
        """Cash falls whenever margin is posted, with no loss. Measured on cash
        the second order below would be judged against a much smaller base."""
        env = await make_env(
            session_factory,
            "PTLIMCASHUSD",
            starting_balance="10000",
            max_position=D("10"),
        )
        await env.order("buy", "0.45")  # ~$900 posted; cash now ~$9,100
        # Position -> 0.49 units = $980, which is 9.8% of *equity* (~$9,998.6).
        # Judged against the ~$9,098 of cash left it would be 10.8% and fail.
        await env.order("buy", "0.04")
        with pytest.raises(MaxPositionSizeExceededError):
            await env.order("buy", "0.02")  # -> $1,020, 10.2% of equity

    async def test_exposure_counts_a_short_by_its_absolute_notional(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(
            session_factory,
            "PTLIMSHORTUSD",
            starting_balance="10000",
            max_exposure=D("30"),
        )
        await env.order("sell", "1.4")  # ~$2,800 of short notional
        with pytest.raises(MaxExposureExceededError):
            await env.order("sell", "0.2")  # ~$3,200 > 30% of ~$10,000
        risk = await env.service.risk_summary(env.account_id)
        assert num(risk.current_exposure_pct) == pytest.approx(28.0, rel=0.01)

    async def test_the_risk_summary_reports_equity_margin_and_effective_leverage(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTRISKSUMUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")  # notional 10005, margin 2001
        risk = await env.service.risk_summary(env.account_id)
        cash = 100000 - 2001.0 - 10.005
        assert num(risk.balance) == pytest.approx(cash)
        assert num(risk.margin_in_use) == pytest.approx(2001.0)
        # equity = cash + margin + unrealized ((2000 - 2001) * 5)
        assert num(risk.equity) == pytest.approx(cash + 2001.0 - 5.0)
        assert num(risk.total_notional) == pytest.approx(5 * 2000.0)
        assert num(risk.effective_leverage) == pytest.approx(10000.0 / num(risk.equity))
        assert num(risk.max_leverage) == 5

        summary = await env.service.summary(env.account_id)
        assert num(summary.total_equity) == pytest.approx(num(risk.equity))
        assert num(summary.margin_in_use) == pytest.approx(2001.0)
        assert num(summary.unrealized_pnl) == pytest.approx(-5.0)

    async def test_a_shorts_loss_counts_toward_the_drawdown_limit(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(
            session_factory,
            "PTDDSHORTUSD",
            starting_balance="10000",
            price="500",
            max_drawdown=D("20"),
        )
        await env.order("sell", "10")  # ~$4,997.5 short at 1x
        await env.price("750")  # short loses ~$2,502.5: equity ~7,492 = a 25% drawdown
        with pytest.raises(TradingHaltedError):
            await env.order("sell", "0.001")
        assert (await env.account()).trading_halted is True

    async def test_a_halted_account_can_still_cover_a_short_but_not_open_one(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(
            session_factory,
            "PTHALTCOVERUSD",
            starting_balance="10000",
            price="500",
            max_drawdown=D("20"),
        )
        await env.order("sell", "10")
        await env.price("750")
        with pytest.raises(TradingHaltedError):
            await env.order("sell", "0.001")
        covered = await env.order("buy", "10", reduce_only=True)
        assert covered.realized_pnl is not None and num(covered.realized_pnl) < 0
        assert await env.position() is None
        assert (await env.account()).trading_halted is True  # closing does not un-halt

    async def test_the_halt_raises_an_alert(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D4: the kill switch halts new risk *and alerts*."""
        alerts: list[dict[str, object]] = []
        monkeypatch.setattr(
            "app.services.paper_trading.capture_trading_halted",
            lambda account_id, **kwargs: alerts.append({"account_id": account_id, **kwargs}),
        )
        env = await make_env(
            session_factory, "PTHALTALERTUSD", starting_balance="10000", max_drawdown=D("20")
        )
        await env.order("buy", "4")
        await env.price("1000")
        with pytest.raises(TradingHaltedError):
            await env.order("buy", "0.001")
        assert len(alerts) == 1
        assert alerts[0]["account_id"] == str(env.account_id)
        assert num(alerts[0]["max_drawdown_pct"]) == 20


@pytest.mark.asyncio
class TestUnleveragedLongIsUnchanged:
    """The generalization must not change anything at leverage 1: a 1x long is
    the position this engine has always had."""

    async def test_a_1x_long_reproduces_the_original_cash_accounting_exactly(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTREGRESSIONUSD", price="1000")
        buy = await env.order("buy", "10")
        # The original arithmetic, unchanged: fill 1000.5, notional 10005, fee 10.005.
        assert num(buy.fill_price) == pytest.approx(1000.5)
        assert num(buy.notional) == pytest.approx(10005.0)
        assert num(buy.fee_applied) == pytest.approx(10.005)
        assert buy.position_side == "long"
        assert num(buy.leverage) == 1
        assert num(buy.margin_applied) == pytest.approx(10005.0)  # the whole notional
        assert buy.realized_pnl is None

        account = await env.account()
        assert num(account.balance) == pytest.approx(100000 - 10005.0 - 10.005)
        assert num(account.realized_pnl) == pytest.approx(-10.005)

        position = await env.position()
        assert position is not None
        assert position.side == "long"
        assert num(position.margin) == pytest.approx(10005.0)
        assert position.liquidation_price is None  # a 1x long cannot be liquidated
        assert position.liquidation_distance_pct is None

        # Position value is still quantity * price: equity = cash + 10 * 1100.
        await env.price("1100")
        summary = await env.service.summary(env.account_id)
        assert num(summary.total_equity) == pytest.approx(num(account.balance) + 10 * 1100.0)
        assert num(summary.unrealized_pnl) == pytest.approx((1100 - 1000.5) * 10)

        sell = await env.order("sell", "10")
        # sell fills 1100 * 0.9995 = 1099.45; realized (1099.45 - 1000.5) * 10 - fee 10.9945
        assert sell.realized_pnl is not None
        assert num(sell.realized_pnl) == pytest.approx(989.5 - 10.9945)
        final = await env.account()
        assert num(final.balance) == pytest.approx(
            100000 - 10005.0 - 10.005 + 10 * 1099.45 - 10.9945
        )
        assert num(final.balance) == pytest.approx(100000 + num(final.realized_pnl))

    async def test_a_1x_long_is_never_liquidated_even_if_price_collapses(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTNOLIQUSD", price="1000")
        await env.order("buy", "10")
        await env.price("1")
        position = await env.position()
        assert position is not None
        assert position.liquidation_price is None


@pytest.mark.asyncio
class TestAutomatedCaller:
    """What an order declared `automated=True` may do (M3-E5-T3). The automated
    strategy now trades both directions, so the shared order path no longer
    refuses shorts; it instead enforces the two things that must always hold
    for an automated entry: exactly the account's fixed `strategy_leverage`, and
    a stop-loss. Everything else (halt, limits) is the same code as a manual
    order, checked in `test_strategy_scheduler.py` end to end."""

    async def test_an_automated_entry_at_the_fixed_leverage_with_a_stop_opens_a_long_or_a_short(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTAUTOENTRYUSD", max_leverage="5")
        long_order = await env.automated("buy", "2", leverage="2", stop_loss_price="1900")
        assert long_order.position_side == "long"
        assert num(long_order.leverage) == 2
        await env.automated("sell", "2", reduce_only=True)
        assert await env.position() is None

        short_order = await env.automated("sell", "2", leverage="2", stop_loss_price="2100")
        assert short_order.position_side == "short"  # shorting IS reachable now
        assert num(short_order.leverage) == 2
        position = await env.position()
        assert position is not None
        assert position.side == "short"
        assert num(position.stop_loss_price or 0) == 2100

    async def test_an_automated_entry_at_any_other_leverage_is_refused(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTAUTOLEVUSD", max_leverage="10")
        for leverage in ("5", "3", "1"):  # the account's strategy_leverage is the default 2
            with pytest.raises(AutomatedOrderRestrictedError) as error:
                await env.automated("buy", "1", leverage=leverage, stop_loss_price="1900")
            assert "strategy_leverage" in str(error.value)
        with pytest.raises(AutomatedOrderRestrictedError):
            await env.automated("sell", "1", stop_loss_price="2100")  # none named = 1x
        assert await env.position() is None

    async def test_an_automated_entry_without_a_stop_loss_is_refused_in_both_directions(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTAUTONOSTOPUSD", max_leverage="5")
        for side in ("buy", "sell"):
            with pytest.raises(AutomatedOrderRestrictedError) as error:
                await env.automated(side, "1", leverage="2")
            assert "stop-loss" in str(error.value)
        assert await env.position() is None

    async def test_the_stop_loss_must_still_be_valid_for_the_side(
        self, session_factory: SessionFactory
    ) -> None:
        """Direction-aware validation is the shared path's own: a short's stop
        below the price is rejected exactly as for a manual short."""
        env = await make_env(session_factory, "PTAUTOSTOPSIDEUSD", max_leverage="5")
        with pytest.raises(InvalidStopLossPriceError):
            await env.automated("sell", "1", leverage="2", stop_loss_price="1900")
        with pytest.raises(InvalidStopLossPriceError):
            await env.automated("buy", "1", leverage="2", stop_loss_price="2100")

    async def test_an_automated_order_never_adds_to_a_position(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTAUTOADDUSD", max_leverage="5")
        await env.automated("buy", "1", leverage="2", stop_loss_price="1900")
        with pytest.raises(AutomatedOrderRestrictedError) as error:
            await env.automated("buy", "1", leverage="2", stop_loss_price="1900")
        assert "never adds" in str(error.value)
        position = await env.position()
        assert position is not None
        assert num(position.quantity) == 1

    async def test_an_automated_order_can_close_a_manual_position_of_either_side(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTAUTOCLOSEUSD", max_leverage="10")
        await env.order("buy", "2", leverage="5")  # a manual leveraged long
        await env.automated("sell", "2", reduce_only=True)
        assert await env.position() is None
        await env.order("sell", "2", leverage="5")  # a manual leveraged short
        await env.automated("buy", "2", reduce_only=True)
        assert await env.position() is None

    async def test_an_automated_close_that_finds_nothing_open_fails_instead_of_opening_a_short(
        self, session_factory: SessionFactory
    ) -> None:
        """The race a stop-loss or a liquidation creates: the position is
        already gone. A reduce-only close must fail closed, never open the
        opposite side."""
        env = await make_env(session_factory, "PTAUTORACEUSD", max_leverage="5")
        with pytest.raises(ReduceOnlyViolationError):
            await env.automated("sell", "1", reduce_only=True)
        with pytest.raises(ReduceOnlyViolationError):
            await env.automated("buy", "1", reduce_only=True)
        assert await env.position() is None

    async def test_a_default_order_request_carries_no_leverage_and_is_not_reduce_only(self) -> None:
        request = PaperOrderRequest(symbol="ETHUSD", side="buy", quantity=D("1"))
        assert request.leverage is None
        assert request.reduce_only is False


@pytest.mark.asyncio
class TestOrderActorIsRequired:
    """`place_order` must be told who is placing the order: a real `user_id`
    (manual) or `automated=True` (the strategy), and exactly one. Naming neither
    used to be classified as automated by inference; under an explicit flag it
    would silently have become the *lenient* manual path, so it is refused."""

    async def test_an_order_naming_neither_a_user_nor_automated_is_refused_before_anything_happens(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTACTORNONEUSD")
        cash_before = num((await env.account()).balance)
        with pytest.raises(ValueError, match="neither"):
            # The base-class method itself (the test service defaults a user in).
            await PaperTradingService.place_order(
                env.service,
                env.account_id,
                PaperOrderRequest(symbol=env.symbol, side="buy", quantity=D("1")),
            )
        assert await env.position() is None
        assert num((await env.account()).balance) == cash_before
        orders = await env.service.list_orders(
            env.account_id, sort="created_at", direction="asc", limit=5, offset=0
        )
        assert orders.total == 0

    async def test_an_order_that_is_both_manual_and_automated_is_refused(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTACTORBOTHUSD")
        with pytest.raises(ValueError, match="both"):
            await PaperTradingService.place_order(
                env.service,
                env.account_id,
                PaperOrderRequest(symbol=env.symbol, side="buy", quantity=D("1")),
                user_id=env.user_id,
                automated=True,
            )
        assert await env.position() is None

    async def test_exactly_one_actor_works_either_way(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTACTORONEUSD")
        await PaperTradingService.place_order(
            env.service,
            env.account_id,
            PaperOrderRequest(symbol=env.symbol, side="buy", quantity=D("1")),
            user_id=env.user_id,
        )
        await PaperTradingService.place_order(
            env.service,
            env.account_id,
            PaperOrderRequest(symbol=env.symbol, side="sell", quantity=D("1"), reduce_only=True),
            automated=True,
        )
        assert await env.position() is None

    def test_every_place_order_call_in_the_application_names_its_actor(self) -> None:
        """Grep-verifiable: each `.place_order(` call in `app/` passes `user_id=`
        (manual) or `automated=True` (the strategy), and `automated=True` appears
        only in the strategy module. The classification the review asked for."""
        import ast
        from pathlib import Path

        app_dir = Path(__file__).parents[2] / "app"
        manual: list[str] = []
        automated: list[str] = []
        unclassified: list[str] = []
        for path in app_dir.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "place_order"
                ):
                    continue
                where = f"{path.relative_to(app_dir)}:{node.lineno}"
                keywords = {kw.arg: kw.value for kw in node.keywords}
                is_auto = isinstance(keywords.get("automated"), ast.Constant) and (
                    keywords["automated"].value is True  # type: ignore[union-attr]
                )
                if is_auto and "user_id" not in keywords:
                    automated.append(where)
                elif "user_id" in keywords and "automated" not in keywords:
                    manual.append(where)
                else:
                    unclassified.append(where)
        assert unclassified == []
        assert manual == ["api/v1/endpoints/paper_trading.py:327"]
        assert sorted(automated) == [
            "services/paper_trading_strategy.py:465",
            "services/paper_trading_strategy.py:539",
        ]


@pytest.mark.asyncio
class TestAutomatedShortHitsTheSameLimitsAsAnAutomatedLong:
    """Short-specific proof, not inherited from the long-side tests: each risk
    limit is forced with an automated SHORT and the identical automated LONG, and
    the two must be rejected by the same error, with the same numbers, and accepted
    at the same size just under the limit. (Scheduler-level counterparts are in
    `test_strategy_scheduler.py::TestSharesExistingRiskLimits`.)"""

    SIDES = (("buy", "1900", "long"), ("sell", "2100", "short"))

    @pytest.mark.parametrize(("side", "stop", "label"), SIDES)
    async def test_position_size_limit(
        self, session_factory: SessionFactory, side: str, stop: str, label: str
    ) -> None:
        env = await make_env(
            session_factory,
            f"PTAUTOPOS{label.upper()}USD",
            starting_balance="10000",
            max_leverage="5",
            max_position=D("10"),  # $1,000 of notional on $10,000 of equity
        )
        # 1 unit is ~$2,000 of notional (only ~$1,000 of margin at the strategy's 2x):
        # over the 10% limit in BOTH directions, because the limit is on notional.
        with pytest.raises(MaxPositionSizeExceededError) as error:
            await env.automated(side, "1", leverage="2", stop_loss_price=stop)
        assert error.value.code == "max_position_size_exceeded"
        assert "max position size" in str(error.value)
        assert await env.position() is None
        # 0.4 unit (~$800 notional) is under it, in both directions.
        order = await env.automated(side, "0.4", leverage="2", stop_loss_price=stop)
        assert order.position_side == label

    @pytest.mark.parametrize(("side", "stop", "label"), SIDES)
    async def test_exposure_limit(
        self, session_factory: SessionFactory, side: str, stop: str, label: str
    ) -> None:
        env = await make_env(
            session_factory,
            f"PTAUTOEXP{label.upper()}USD",
            starting_balance="10000",
            max_leverage="5",
            max_exposure=D("50"),  # $5,000 of notional on $10,000 of equity
        )
        # ~$6,000 of notional (3 units) is only ~$3,000 of margin at 2x, but the
        # ceiling is on notional: rejected for the short exactly as for the long.
        with pytest.raises(MaxExposureExceededError) as error:
            await env.automated(side, "3", leverage="2", stop_loss_price=stop)
        assert error.value.code == "max_exposure_exceeded"
        assert await env.position() is None
        # ~$4,000 (2 units) fits.
        order = await env.automated(side, "2", leverage="2", stop_loss_price=stop)
        assert order.position_side == label

    @pytest.mark.parametrize(("side", "stop", "label"), SIDES)
    async def test_drawdown_limit_halts_and_rejects_the_entry(
        self, session_factory: SessionFactory, side: str, stop: str, label: str
    ) -> None:
        """An account already 25% below its equity peak (limit 20%) takes no new
        automated entry in either direction, and the halt is persisted."""
        env = await make_env(
            session_factory,
            f"PTAUTODD{label.upper()}USD",
            starting_balance="10000",
            price="500",
            max_leverage="5",
            max_drawdown=D("20"),
        )
        other = f"PTAUTODD{label.upper()}OTHERUSD"  # the strategy's market is a different one
        await seed_market(session_factory, symbol=other)
        await env.price("500", other)
        await env.order("buy", "10")  # a manual long: ~$5,000, equity ~$9,995
        await env.price("250")  # loses ~$2,500 -> equity ~7,490, a ~25% drawdown
        with pytest.raises(TradingHaltedError) as error:
            await env.automated(
                side,
                "1",
                symbol=other,
                leverage="2",
                stop_loss_price="450" if side == "buy" else "550",
            )
        assert error.value.code == "trading_halted"
        assert (await env.account()).trading_halted is True
        positions = (await env.service.list_positions(env.account_id)).positions
        assert [(p.symbol, p.side) for p in positions] == [
            (env.symbol, "long")
        ]  # only the manual long

    async def test_long_and_short_are_rejected_with_the_same_error_type_and_numbers(
        self, session_factory: SessionFactory
    ) -> None:
        errors = {}
        for side, stop, label in self.SIDES:
            env = await make_env(
                session_factory,
                f"PTAUTOSAME{label.upper()}USD",
                starting_balance="10000",
                max_leverage="5",
                max_exposure=D("50"),
            )
            with pytest.raises(MaxExposureExceededError) as error:
                await env.automated(side, "3", leverage="2", stop_loss_price=stop)
            errors[label] = error.value
        assert type(errors["long"]) is type(errors["short"])
        assert errors["long"].code == errors["short"].code
        # Same resulting exposure and percentage in the message, to the cent.
        assert (
            str(errors["long"]).split("total exposure to ")[1].split(" ")[0][:5]
            == str(errors["short"]).split("total exposure to ")[1].split(" ")[0][:5]
        )


@pytest.mark.asyncio
class TestStrategyLeverageConfig:
    """`strategy_leverage` is one fixed, validated, per-account number."""

    async def test_a_new_account_defaults_to_2x_within_its_own_ceiling(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSLDEFUSD")
        assert num((await env.account()).strategy_leverage) == 2
        capped = await make_env(session_factory, "PTSLDEF2USD", max_leverage="1")
        assert num((await capped.account()).strategy_leverage) == 1  # never above max_leverage

    async def test_it_can_be_configured_within_the_accounts_maximum(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSLCFGUSD", max_leverage="5")
        updated = await env.service.update_strategy_config(
            env.account_id,
            PaperStrategyConfigUpdateRequest(leverage=D("3")),
            user_id=env.user_id,
        )
        assert num(updated.strategy_leverage) == 3

    async def test_it_cannot_exceed_the_accounts_max_leverage(
        self, session_factory: SessionFactory
    ) -> None:
        env = await make_env(session_factory, "PTSLMAXUSD", max_leverage="3")
        with pytest.raises(StrategyLeverageExceedsMaximumError):
            await env.service.update_strategy_config(
                env.account_id,
                PaperStrategyConfigUpdateRequest(leverage=D("4")),
                user_id=env.user_id,
            )
        assert num((await env.account()).strategy_leverage) == 2  # unchanged

    async def test_the_mandatory_stop_loss_must_fit_inside_the_liquidation_distance(
        self, session_factory: SessionFactory
    ) -> None:
        """At 20x a position is liquidated ~4.7% away, so the default 5%
        stop-loss could never fire before liquidation: refused at config time,
        not discovered as a rejected order later."""
        env = await make_env(session_factory, "PTSLSTOPUSD", max_leverage="20")
        with pytest.raises(StrategyStopBeyondLiquidationError) as error:
            await env.service.update_strategy_config(
                env.account_id,
                PaperStrategyConfigUpdateRequest(leverage=D("20")),
                user_id=env.user_id,
            )
        assert error.value.code == "strategy_stop_beyond_liquidation"
        # A tighter stop, or a lower leverage, is fine.
        await env.service.update_strategy_config(
            env.account_id,
            PaperStrategyConfigUpdateRequest(leverage=D("20"), default_stop_loss_pct=D("3")),
            user_id=env.user_id,
        )
        await env.service.update_strategy_config(
            env.account_id,
            PaperStrategyConfigUpdateRequest(leverage=D("10"), default_stop_loss_pct=D("5")),
            user_id=env.user_id,
        )

    async def test_an_explicit_null_leverage_is_rejected_at_the_schema(self) -> None:
        with pytest.raises(ValueError, match="cannot be explicitly cleared"):
            PaperStrategyConfigUpdateRequest.model_validate({"leverage": None})
        with pytest.raises(ValueError):
            PaperStrategyConfigUpdateRequest(leverage=D("0.5"))
        with pytest.raises(ValueError):
            PaperStrategyConfigUpdateRequest(leverage=D("201"))


@pytest.mark.asyncio
class TestConcurrencyGuardCoversMarginState:
    async def test_the_guard_matches_on_state_version_not_just_balance(
        self, session_factory: SessionFactory
    ) -> None:
        """A liquidation forfeits margin while returning no cash, so `balance`
        is unchanged; a guard on balance alone would let a stale writer through.
        The version is what catches it."""
        env = await make_env(session_factory, "PTGUARDUSD")
        repository = env.service.account_repository
        account = await repository.get_by_id(env.account_id)
        assert account is not None
        assert account.state_version == 0

        # A writer that changes nothing about cash but is a real trade effect.
        first = await repository.try_apply_trade_effects(
            env.account_id,
            expected_balance=account.balance,
            expected_trading_halted=account.trading_halted,
            expected_state_version=0,
            new_balance=account.balance,
            new_realized_pnl=D("-25"),
            new_peak_balance=account.peak_balance,
            new_trading_halted=False,
        )
        assert first is not None
        assert first.state_version == 1

        # A second writer that read the account before that: same balance and
        # halted flag, stale version. It must lose.
        stale = await repository.try_apply_trade_effects(
            env.account_id,
            expected_balance=account.balance,
            expected_trading_halted=account.trading_halted,
            expected_state_version=0,
            new_balance=account.balance,
            new_realized_pnl=D("0"),
            new_peak_balance=account.peak_balance,
            new_trading_halted=False,
        )
        assert stale is None
        assert num((await env.account()).realized_pnl) == -25
