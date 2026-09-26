"""Liquidation, stop-loss and take-profit for short and leveraged positions,
driven by real events on the bus through the same `StopLossTakeProfitMonitor`
long positions always used.

Expected numbers are worked out by hand. The two positions used throughout:

- a **5x long** of 5 units opened at a $2000 quote: fill $2001 (5 bps
  slippage), margin `10005 / 5 = 2001`, bankruptcy `2001 * 0.8 = 1600.8`,
  liquidation `1600.8 / 0.9975 = 1604.81`;
- a **5x short** of 5 units at a $2000 quote: fill $1999, margin `9995 / 5 =
  1999`, bankruptcy `1999 * 1.2 = 2398.8`, liquidation `2398.8 / 1.0025 =
  2392.82`.

A liquidation fills at the *mark* price with the wider triggered slippage
(25 bps), forfeits the position's whole remaining margin (returning no cash),
and is never charged beyond that margin.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.events.bus import EventBus
from app.marketdata.bus_events import TickerUpdated, TradeEventReceived
from app.marketdata.models import TickerEvent, TradeEvent
from app.paper_trading import monitor as monitor_module
from tests.conftest import SessionFactory
from tests.paper_trading.test_monitor import build_monitor
from tests.paper_trading.test_short_and_leverage import Env, make_env, num

D = Decimal
LONG_LIQ = 2001 * 0.8 / 0.9975  # ~1604.81
SHORT_LIQ = 1999 * 1.2 / 1.0025  # ~2392.82


@pytest.fixture(autouse=True)
def _use_test_engine(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr(monitor_module, "get_engine", lambda: engine)


async def publish(bus: EventBus, symbol: str, *, last: str | None, mark: str | None = None) -> None:
    await bus.publish(
        TickerUpdated(
            source="test",
            ticker=TickerEvent(
                exchange="delta",
                symbol=symbol,
                event_time=datetime.now(UTC),
                last_price=D(last) if last is not None else None,
                mark_price=D(mark) if mark is not None else None,
            ),
        )
    )
    await bus.drain()


async def monitored_env(session_factory: SessionFactory, symbol: str, **kwargs: object) -> Env:
    env = await make_env(session_factory, symbol, **kwargs)  # type: ignore[arg-type]
    build_monitor(env.service.state_manager).attach(env.bus)
    return env


async def closing_orders(env: Env):  # noqa: ANN201
    orders = await env.service.list_orders(
        env.account_id, sort="created_at", direction="asc", limit=50, offset=0
    )
    return [o for o in orders.orders if o.trigger_reason is not None]


@pytest.mark.asyncio
class TestLiquidationOfALong:
    async def test_a_long_is_liquidated_when_the_mark_price_reaches_its_liquidation_price(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQLONGUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")
        position = await env.position()
        assert position is not None and position.liquidation_price is not None
        assert num(position.liquidation_price) == pytest.approx(LONG_LIQ)
        cash_before = num((await env.account()).balance)

        # Mark $1604 is at/below the $1604.81 liquidation price and above the
        # $1600.8 bankruptcy price.
        await publish(env.bus, env.symbol, last="1610", mark="1604")

        assert await env.position() is None
        [order] = await closing_orders(env)
        assert order.trigger_reason == "liquidation"
        assert order.side == "sell" and order.position_side == "long"
        assert order.trigger_price_basis == "mark"
        assert num(order.raw_price) == 1604.0  # priced on the MARK, not the $1610 last
        # The wider *triggered* slippage: 1604 * (1 - 25/10000), not the manual 5 bps.
        assert num(order.fill_price) == pytest.approx(1604 * 0.9975)
        assert num(order.slippage_applied) == pytest.approx(1604 * 0.0025)
        assert order.reduce_only is True
        assert order.gapped_through_bankruptcy is False

        # Full margin forfeiture (D6): the $2001 posted is gone, no cash returned.
        assert num(order.margin_applied) == pytest.approx(2001.0)
        assert order.realized_pnl is not None
        assert num(order.realized_pnl) == pytest.approx(-2001.0)
        account = await env.account()
        assert num(account.balance) == pytest.approx(cash_before)  # nothing came back
        assert num(account.realized_pnl) == pytest.approx(-10.005 - 2001.0)
        # Flat again, so cash still reconciles against starting balance + realized PnL.
        assert num(account.balance) == pytest.approx(100000 + num(account.realized_pnl))

    async def test_liquidation_runs_on_the_mark_price_not_the_last_price(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQMARKUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")
        # A wick: the LAST price prints far below the liquidation price while
        # the mark (the exchange's own liquidation trigger) stays healthy.
        await publish(env.bus, env.symbol, last="1500", mark="1700")
        assert await env.position() is not None
        assert await closing_orders(env) == []

    async def test_a_ticker_with_no_mark_price_falls_back_to_last_and_says_so(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQFALLUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")
        await publish(env.bus, env.symbol, last="1600", mark=None)
        [order] = await closing_orders(env)
        assert order.trigger_reason == "liquidation"
        assert order.trigger_price_basis == "last_fallback"

    async def test_a_gap_through_the_bankruptcy_price_is_recorded_and_the_loss_stays_capped(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQGAPUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")
        cash_before = num((await env.account()).balance)
        await publish(env.bus, env.symbol, last="1500", mark="1500")  # far below $1600.8
        [order] = await closing_orders(env)
        assert order.gapped_through_bankruptcy is True
        # Isolated margin: never charged beyond the margin actually posted.
        assert order.realized_pnl is not None
        assert num(order.realized_pnl) == pytest.approx(-2001.0)
        assert num((await env.account()).balance) == pytest.approx(cash_before)

    async def test_a_price_above_the_liquidation_price_does_not_liquidate(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQNOTUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")
        await publish(env.bus, env.symbol, last="1650", mark="1610")  # just above $1604.81
        assert await env.position() is not None
        assert await closing_orders(env) == []

    async def test_a_trade_event_never_triggers_a_liquidation(
        self, session_factory: SessionFactory
    ) -> None:
        """A trade carries no mark price, so it has nothing to judge a
        liquidation by (it can still trip a stop-loss)."""
        env = await monitored_env(session_factory, "PTLIQTRADEUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")
        await env.bus.publish(
            TradeEventReceived(
                source="test",
                trade=TradeEvent(
                    exchange="delta",
                    symbol=env.symbol,
                    event_time=datetime.now(UTC),
                    side="sell",
                    price=D("1500"),
                    size=D("1"),
                ),
            )
        )
        await env.bus.drain()
        assert await env.position() is not None
        assert await closing_orders(env) == []


@pytest.mark.asyncio
class TestLiquidationOfAShort:
    async def test_a_short_is_liquidated_when_the_mark_price_rises_to_its_liquidation_price(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQSHORTUSD", max_leverage="5")
        await env.order("sell", "5", leverage="5")
        position = await env.position()
        assert position is not None and position.liquidation_price is not None
        assert num(position.liquidation_price) == pytest.approx(SHORT_LIQ)
        cash_before = num((await env.account()).balance)

        await publish(env.bus, env.symbol, last="2380", mark="2395")

        assert await env.position() is None
        [order] = await closing_orders(env)
        assert order.trigger_reason == "liquidation"
        assert order.side == "buy" and order.position_side == "short"
        # A buy fills against the trader at the wider 25 bps: 2395 * 1.0025.
        assert num(order.fill_price) == pytest.approx(2395 * 1.0025)
        assert order.gapped_through_bankruptcy is False  # $2395 < $2398.8 bankruptcy
        assert num(order.margin_applied) == pytest.approx(1999.0)
        assert order.realized_pnl is not None
        assert num(order.realized_pnl) == pytest.approx(-1999.0)
        assert num((await env.account()).balance) == pytest.approx(cash_before)

    async def test_a_short_gapping_above_its_bankruptcy_price_is_flagged(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQSHORTGAPUSD", max_leverage="5")
        await env.order("sell", "5", leverage="5")
        await publish(env.bus, env.symbol, last="2600", mark="2600")
        [order] = await closing_orders(env)
        assert order.gapped_through_bankruptcy is True
        assert order.realized_pnl is not None
        assert num(order.realized_pnl) == pytest.approx(-1999.0)  # capped at the margin

    async def test_a_lower_leverage_short_survives_a_move_that_liquidates_a_higher_one(
        self, session_factory: SessionFactory
    ) -> None:
        low = await monitored_env(session_factory, "PTLIQLOWLEVUSD", max_leverage="5")
        await low.order("sell", "1", leverage="2")
        await publish(low.bus, low.symbol, last="2395", mark="2395")
        assert await low.position() is not None  # 2x: liquidation ~ $2,985


@pytest.mark.asyncio
class TestTriggerOrder:
    async def test_liquidation_is_checked_before_the_stop_loss_and_only_one_order_results(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQFIRSTUSD", max_leverage="5")
        # A stop-loss at $1700 sits above the $1604.81 liquidation price (valid).
        await env.order("buy", "5", leverage="5", stop_loss_price="1700")
        await publish(env.bus, env.symbol, last="1600", mark="1600")  # crosses both
        orders = await closing_orders(env)
        assert [o.trigger_reason for o in orders] == ["liquidation"]

    async def test_a_stop_loss_fires_on_the_last_price_when_the_mark_has_not_reached_liquidation(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTLIQSTOPUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5", stop_loss_price="1700")
        await publish(env.bus, env.symbol, last="1690", mark="1720")
        [order] = await closing_orders(env)
        assert order.trigger_reason == "stop_loss"
        assert order.trigger_price_basis is None  # only liquidations record a basis
        # An ordinary triggered exit: last price with the wider triggered slippage,
        # and the margin comes back with the PnL (not forfeited).
        assert num(order.fill_price) == pytest.approx(1690 * 0.9975)
        assert order.realized_pnl is not None
        assert num(order.realized_pnl) == pytest.approx(
            (1690 * 0.9975 - 2001) * 5 - 1690 * 0.9975 * 5 * 0.001
        )
        account = await env.account()
        assert num(account.balance) == pytest.approx(100000 + num(account.realized_pnl))

    async def test_a_shorts_stop_loss_and_take_profit_trigger_in_the_short_direction(
        self, session_factory: SessionFactory
    ) -> None:
        stop = await monitored_env(session_factory, "PTSHORTSTOPUSD")
        await stop.order("sell", "2", stop_loss_price="2100", take_profit_price="1800")
        await publish(stop.bus, stop.symbol, last="2100")
        [stopped] = await closing_orders(stop)
        assert stopped.trigger_reason == "stop_loss"
        assert stopped.side == "buy"
        assert num(stopped.fill_price) == pytest.approx(2100 * 1.0025)

        take = await monitored_env(session_factory, "PTSHORTTAKEUSD")
        await take.order("sell", "2", stop_loss_price="2100", take_profit_price="1800")
        await publish(take.bus, take.symbol, last="1800")
        [taken] = await closing_orders(take)
        assert taken.trigger_reason == "take_profit"
        assert taken.realized_pnl is not None and num(taken.realized_pnl) > 0

    async def test_neither_threshold_fires_for_a_short_between_them(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTSHORTBETWEENUSD")
        await env.order("sell", "2", stop_loss_price="2100", take_profit_price="1800")
        await publish(env.bus, env.symbol, last="2050")  # a long's stop would be crossed here
        await publish(env.bus, env.symbol, last="1850")  # ...and a long's take-profit here
        assert await env.position() is not None
        assert await closing_orders(env) == []


@pytest.mark.asyncio
class TestHaltAndLiquidation:
    async def test_a_halted_account_is_still_liquidated_and_still_stops_out(
        self, session_factory: SessionFactory
    ) -> None:
        """D4: the halt blocks new risk only; nothing may stop a liquidation,
        and a triggered exit is never refused (an account that has just
        breached its drawdown limit must not be left fully exposed)."""
        env = await monitored_env(session_factory, "PTHALTLIQUSD", max_leverage="5")
        await env.order("buy", "5", leverage="5")
        account = await env.service.account_repository.get_by_id(env.account_id)
        assert account is not None
        await env.service.account_repository.update(account, {"trading_halted": True})

        await publish(env.bus, env.symbol, last="1600", mark="1600")
        [order] = await closing_orders(env)
        assert order.trigger_reason == "liquidation"
        assert await env.position() is None

    async def test_a_halted_account_still_honours_a_stop_loss(
        self, session_factory: SessionFactory
    ) -> None:
        env = await monitored_env(session_factory, "PTHALTSTOPUSD")
        await env.order("buy", "5", stop_loss_price="1900")
        account = await env.service.account_repository.get_by_id(env.account_id)
        assert account is not None
        await env.service.account_repository.update(account, {"trading_halted": True})

        await publish(env.bus, env.symbol, last="1890")
        [order] = await closing_orders(env)
        assert order.trigger_reason == "stop_loss"
        assert await env.position() is None
        assert (await env.account()).trading_halted is True  # closing does not un-halt


# The liquidation-versus-manual-close race lives in
# `tests/paper_trading/test_concurrency_postgres.py`: it needs genuinely
# separate database connections, which this suite's single-connection SQLite
# engine cannot provide (it would pass while the code was wrong).
