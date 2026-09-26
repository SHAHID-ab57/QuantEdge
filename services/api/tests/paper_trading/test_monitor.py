"""Tests for `StopLossTakeProfitMonitor` — the event-bus subscriber that
closes a position automatically, through the exact same fill model and
atomic concurrency guard a manual close uses, the instant a live price
event crosses its stop-loss or take-profit.

Mirrors `tests/services/test_grading_scheduler.py`'s own convention:
`get_engine` monkeypatched to the test's in-memory engine, since this
monitor never goes through `get_db`/FastAPI's dependency overrides —
there is no HTTP request behind a bus event.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.events.bus import EventBus
from app.paper_trading import monitor as monitor_module
from app.paper_trading.monitor import StopLossTakeProfitMonitor
from app.repositories.paper_trading import PaperPositionRepository
from app.schemas.paper_trading import PaperAccountCreateRequest, PaperOrderRequest
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory
from tests.paper_trading.test_service import (
    DEFAULT_STRATEGY_CONFIDENCE_THRESHOLD_PCT,
    DEFAULT_STRATEGY_STOP_LOSS_PCT,
    FEE_BPS,
    GENEROUS_MAX_PCT,
    MAX_ORDER_ATTEMPTS,
    SLIPPAGE_BPS,
    STALENESS_THRESHOLD,
    TRIGGERED_SLIPPAGE_BPS,
    build_service,
    publish_ticker,
    seed_market,
)


@pytest.fixture(autouse=True)
def _use_test_engine(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr(monitor_module, "get_engine", lambda: engine)


def build_monitor(state_manager: MarketStateManager) -> StopLossTakeProfitMonitor:
    return StopLossTakeProfitMonitor(
        state_manager=state_manager,
        slippage_bps=SLIPPAGE_BPS,
        fee_bps=FEE_BPS,
        triggered_slippage_bps=TRIGGERED_SLIPPAGE_BPS,
        staleness_threshold=STALENESS_THRESHOLD,
        default_max_position_size_pct=GENEROUS_MAX_PCT,
        default_max_exposure_pct=GENEROUS_MAX_PCT,
        default_max_drawdown_pct=GENEROUS_MAX_PCT,
        max_order_attempts=MAX_ORDER_ATTEMPTS,
        default_strategy_confidence_threshold_pct=DEFAULT_STRATEGY_CONFIDENCE_THRESHOLD_PCT,
        default_strategy_default_stop_loss_pct=DEFAULT_STRATEGY_STOP_LOSS_PCT,
    )


@pytest.mark.asyncio
class TestStopLossTrigger:
    async def test_a_stop_loss_closes_the_position_when_price_falls_to_it(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTSLUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        build_monitor(state_manager).attach(bus)

        service = await build_service(session_factory, state_manager)
        await publish_ticker(bus, "PTSLUSD", "1000")
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTSLUSD",
                side="buy",
                quantity=Decimal("10"),
                stop_loss_price=Decimal("900"),
            ),
        )

        # Price falls to exactly the stop-loss level.
        await publish_ticker(bus, "PTSLUSD", "900")

        positions = await service.list_positions(account_id)
        assert positions.positions == []  # closed automatically

        orders = await service.list_orders(
            account_id, sort="created_at", direction="asc", limit=10, offset=0
        )
        assert orders.total == 2  # the original buy, plus the triggered close
        sell_orders = [o for o in orders.orders if o.side == "sell"]
        assert len(sell_orders) == 1
        closing_order = sell_orders[0]
        assert closing_order.side == "sell"
        assert closing_order.trigger_reason == "stop_loss"
        assert float(closing_order.quantity) == pytest.approx(10.0)
        assert closing_order.realized_pnl is not None


@pytest.mark.asyncio
class TestTakeProfitTrigger:
    async def test_a_take_profit_closes_the_position_when_price_rises_to_it(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTTPUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        build_monitor(state_manager).attach(bus)

        service = await build_service(session_factory, state_manager)
        await publish_ticker(bus, "PTTPUSD", "1000")
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTTPUSD",
                side="buy",
                quantity=Decimal("10"),
                take_profit_price=Decimal("1100"),
            ),
        )

        # Price rises to exactly the take-profit level.
        await publish_ticker(bus, "PTTPUSD", "1100")

        positions = await service.list_positions(account_id)
        assert positions.positions == []

        orders = await service.list_orders(
            account_id, sort="created_at", direction="asc", limit=10, offset=0
        )
        assert orders.total == 2
        sell_orders = [o for o in orders.orders if o.side == "sell"]
        assert len(sell_orders) == 1
        closing_order = sell_orders[0]
        assert closing_order.side == "sell"
        assert closing_order.trigger_reason == "take_profit"


@pytest.mark.asyncio
class TestTriggeredSlippageModel:
    async def test_a_triggered_close_applies_the_wider_triggered_slippage_not_the_manual_one(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTTRIGSLIPUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        build_monitor(state_manager).attach(bus)

        service = await build_service(session_factory, state_manager)
        await publish_ticker(bus, "PTTRIGSLIPUSD", "1000")
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTTRIGSLIPUSD",
                side="buy",
                quantity=Decimal("10"),
                take_profit_price=Decimal("1100"),
            ),
        )

        await publish_ticker(bus, "PTTRIGSLIPUSD", "1100")

        orders = await service.list_orders(
            account_id, sort="created_at", direction="asc", limit=10, offset=0
        )
        sell_orders = [o for o in orders.orders if o.side == "sell"]
        assert len(sell_orders) == 1
        closing_order = sell_orders[0]

        # TRIGGERED_SLIPPAGE_BPS=25 (this test module's own constant, 5x
        # SLIPPAGE_BPS=5): fill = 1100 * (1 - 25/10000) = 1097.25, exactly
        # — never the manual model's 1100 * (1 - 5/10000) = 1099.45.
        assert float(closing_order.fill_price) == pytest.approx(1097.25)
        assert float(closing_order.slippage_applied) == pytest.approx(2.75)
        assert float(closing_order.fill_price) != pytest.approx(1099.45)


@pytest.mark.asyncio
class TestTriggeredFillPricesFromTheEventNotAFreshResolve:
    """The test above shares one `MarketStateManager` between the order
    that opens the position and the monitor that closes it — both get fed
    by the same published ticker, so it cannot actually tell "the trigger
    fills from the event's own price" apart from "the trigger re-resolved
    a price through `MarketStateManager`, which just happened to already
    hold the identical number." This test can tell them apart: the
    monitor here is built with its *own*, separate `MarketStateManager`
    that is never attached to the bus and never fed a single event, and
    no candle exists for the symbol either — so `resolve_current_price`
    would raise `NoPriceAvailableError` if `trigger_close` ever called it.
    It doesn't (`app/services/paper_trading.py::trigger_close` only ever
    reads the `quote` parameter the monitor already carries in from the
    triggering event — no `resolve_current_price` call appears anywhere
    in that method); the close still succeeds, which is only possible if
    the fill priced directly from the event itself."""

    async def test_succeeds_even_when_the_monitors_own_state_manager_has_nothing_cached(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTEVENTPRICEUSD")
        bus = EventBus()

        # Fed by the bus — used only to let the initial buy order resolve
        # a live price to fill against.
        order_state_manager = MarketStateManager().attach(bus)
        # Deliberately *not* attached to the bus, and never fed anything —
        # if the monitor's trigger path ever called resolve_current_price
        # against this, it would find no ticker/trade cached and no
        # candle stored, raising NoPriceAvailableError.
        monitor_state_manager = MarketStateManager()
        build_monitor(monitor_state_manager).attach(bus)

        service = await build_service(session_factory, order_state_manager)
        await publish_ticker(bus, "PTEVENTPRICEUSD", "1000")
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTEVENTPRICEUSD",
                side="buy",
                quantity=Decimal("10"),
                stop_loss_price=Decimal("900"),
            ),
        )

        # This ticker crosses the stop-loss. It reaches *both* handlers on
        # this bus: order_state_manager's own (updating its cache, unused
        # by the trigger) and the monitor's (which must price the trigger
        # check and the fill from this event directly, since its own
        # state_manager has nothing to fall back on).
        await publish_ticker(bus, "PTEVENTPRICEUSD", "900")

        positions = await service.list_positions(account_id)
        assert positions.positions == [], (
            "the position should be closed — if trigger_close had instead called "
            "resolve_current_price against the monitor's own (unfed) state manager, "
            "it would raise NoPriceAvailableError, the trigger would be silently "
            "logged and swallowed, and this position would still be open"
        )

        orders = await service.list_orders(
            account_id, sort="created_at", direction="asc", limit=10, offset=0
        )
        sell_orders = [o for o in orders.orders if o.side == "sell"]
        assert len(sell_orders) == 1
        # Fill price is derived from the event's own $900, with the
        # triggered slippage model applied — confirms *which* price fed it.
        assert float(sell_orders[0].fill_price) == pytest.approx(900 * (1 - 25 / 10000))


# `TestConcurrentTriggeredAndManualClose` lived here: a triggered stop-loss
# racing a manual close of the same position. It passed on this suite's
# in-memory SQLite engine, but that engine shares ONE connection between every
# session (`StaticPool`), so two "concurrent" sessions are really one
# transaction and the race was never truly exercised. It now runs, with
# genuinely separate connections, against real PostgreSQL in
# `tests/paper_trading/test_concurrency_postgres.py`, where it (and its
# liquidation and funding siblings) actually found a bug: see that module.


@pytest.mark.asyncio
class TestGapThroughBothLevels:
    """The pathological case this feature's own design makes structurally
    unreachable through the public API (`PaperTradingService
    ._validate_thresholds` enforces `stop_loss_price < take_profit_price`
    whenever both are set) — simulated here by writing directly to the
    position row, bypassing that validation on purpose, to prove the
    monitor's own deterministic tie-break (stop-loss checked first) is
    real, executed code, not just documentation that's never actually
    exercised."""

    async def test_a_single_price_satisfying_both_conditions_triggers_stop_loss_first(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTGAPUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        build_monitor(state_manager).attach(bus)

        service = await build_service(session_factory, state_manager)
        await publish_ticker(bus, "PTGAPUSD", "100")
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="PTGAPUSD", side="buy", quantity=Decimal("10")),
        )

        # Directly force the otherwise-unreachable stop_loss >= take_profit
        # state (never possible through place_order/update_position_thresholds,
        # which always validates the pair together) so a single price can
        # satisfy both `price <= stop_loss_price` (180) and
        # `price >= take_profit_price` (150) at once.
        async with session_factory() as session:
            position_repository = PaperPositionRepository(session)
            position = await position_repository.get_by_account_and_symbol(account_id, "PTGAPUSD")
            assert position is not None
            await position_repository.update(
                position,
                {"stop_loss_price": Decimal("180"), "take_profit_price": Decimal("150")},
            )

        # A single tick lands at 160 — between 150 and 180 — genuinely
        # satisfying both `160 <= 180` and `160 >= 150` simultaneously.
        await publish_ticker(bus, "PTGAPUSD", "160")

        positions = await service.list_positions(account_id)
        assert positions.positions == []  # closed exactly once

        orders = await service.list_orders(
            account_id, sort="created_at", direction="asc", limit=10, offset=0
        )
        assert orders.total == 2
        sell_orders = [o for o in orders.orders if o.side == "sell"]
        assert len(sell_orders) == 1
        closing_order = sell_orders[0]
        assert closing_order.side == "sell"
        # Stop-loss wins the tie-break, deterministically.
        assert closing_order.trigger_reason == "stop_loss"
