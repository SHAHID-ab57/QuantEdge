"""Integration-style tests for `PaperTradingService` — real, realistic
fills (modeled slippage/fee, always applied — proven by exact numbers, not
asserted), fallback-price marking, balance/position rejection rules, and
hand-computed realized/unrealized PnL for a fixture order sequence.

Monetary assertions compare via `pytest.approx` on `float(...)`, not exact
`Decimal` equality: the in-memory SQLite test engine stores `Numeric` via
REAL (floating-point) affinity, not arbitrary-precision decimal storage,
so a value can pick up floating-point noise across a round trip (the same
reason this platform's own target generators, `app/ml_datasets/targets/`,
always compare a candle's own close via `float(...)`). The real Postgres
backend has no such limitation — confirmed directly against the real dev
database while verifying this milestone's own outstanding items (see
`ARCHITECTURE.md` § "Paper Trading").
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.events.bus import EventBus
from app.marketdata.bus_events import TickerUpdated
from app.marketdata.models import TickerEvent
from app.models.candle import Candle
from app.models.exchange import Exchange
from app.models.market import Market
from app.paper_trading.errors import (
    InsufficientBalanceError,
    InsufficientPositionError,
    PaperAccountNotFoundError,
)
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)
from app.schemas.paper_trading import PaperAccountCreateRequest, PaperOrderRequest
from app.services.market_query import MarketNotFoundError
from app.services.paper_trading import PaperTradingService
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory

SLIPPAGE_BPS = 5
FEE_BPS = 10
STALENESS_THRESHOLD = timedelta(seconds=300)


async def seed_market(session_factory: SessionFactory, *, symbol: str) -> None:
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug=f"delta-{symbol.lower()}", country="India")
        session.add(exchange)
        await session.flush()
        session.add(
            Market(
                exchange_id=exchange.id,
                symbol=symbol,
                base_asset=symbol[:3],
                quote_asset=symbol[3:],
                market_type="perpetual",
            )
        )
        await session.commit()


def build_service(
    session_factory: SessionFactory, state_manager: MarketStateManager
) -> PaperTradingService:
    session = session_factory()
    return PaperTradingService(
        account_repository=PaperAccountRepository(session),
        order_repository=PaperOrderRepository(session),
        position_repository=PaperPositionRepository(session),
        market_repository=MarketRepository(session),
        candle_repository=CandleRepository(session),
        state_manager=state_manager,
        slippage_bps=SLIPPAGE_BPS,
        fee_bps=FEE_BPS,
        staleness_threshold=STALENESS_THRESHOLD,
    )


async def publish_ticker(bus: EventBus, symbol: str, price: str) -> None:
    await bus.publish(
        TickerUpdated(
            source="test",
            ticker=TickerEvent(
                exchange="delta",
                symbol=symbol,
                event_time=datetime.now(UTC),
                last_price=Decimal(price),
            ),
        )
    )
    await bus.drain()


@pytest.mark.asyncio
class TestPlaceOrderFillModel:
    async def test_a_buy_fill_differs_from_the_raw_quote_by_exactly_the_modeled_slippage_and_fee(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTFILLUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTFILLUSD", "1000")

        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        order = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTFILLUSD", side="buy", quantity=Decimal("10")),
        )

        assert float(order.raw_price) == pytest.approx(1000.0)
        assert float(order.fill_price) == pytest.approx(1000.5)  # 1000 * (1 + 5/10000)
        assert float(order.slippage_applied) == pytest.approx(0.5)
        assert float(order.fee_applied) == pytest.approx(10.005)  # 10005.0 * 10/10000
        assert order.price_source == "ticker"
        assert order.is_stale_price is False

    async def test_a_sell_fill_is_lower_than_the_raw_quote_by_exactly_the_modeled_slippage(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTSELLFILLUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTSELLFILLUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTSELLFILLUSD", side="buy", quantity=Decimal("1")),
        )

        await publish_ticker(bus, "PTSELLFILLUSD", "1000")
        sell = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTSELLFILLUSD", side="sell", quantity=Decimal("1")),
        )

        assert float(sell.raw_price) == pytest.approx(1000.0)
        assert float(sell.fill_price) == pytest.approx(999.5)  # 1000 * (1 - 5/10000)
        assert float(sell.slippage_applied) == pytest.approx(0.5)

    async def test_a_fallback_priced_fill_is_marked_as_such(
        self, session_factory: SessionFactory
    ) -> None:
        """No live ticker/trade at all — the fill uses the latest stored
        candle's own close, and the order records that plainly rather
        than presenting it as if it used a live price."""
        async with session_factory() as session:
            exchange = Exchange(name="Delta Exchange", slug="delta-ptfallback", country="India")
            session.add(exchange)
            await session.flush()
            market = Market(
                exchange_id=exchange.id,
                symbol="PTFALLBACKUSD",
                base_asset="PTF",
                quote_asset="USD",
                market_type="perpetual",
            )
            session.add(market)
            await session.flush()
            open_time = datetime.now(UTC) - timedelta(minutes=1)
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + timedelta(hours=1),
                    open=Decimal("500"),
                    high=Decimal("500"),
                    low=Decimal("500"),
                    close=Decimal("500"),
                    volume=Decimal("10"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
            await session.commit()

        state_manager = MarketStateManager()  # no live data at all
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        order = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTFALLBACKUSD", side="buy", quantity=Decimal("1")),
        )

        assert order.price_source == "candle_close"
        assert order.is_stale_price is False  # 1 minute old, within the 300s threshold

    async def test_a_stale_fallback_price_is_marked_stale_on_the_fill(
        self, session_factory: SessionFactory
    ) -> None:
        async with session_factory() as session:
            exchange = Exchange(name="Delta Exchange", slug="delta-ptstalefill", country="India")
            session.add(exchange)
            await session.flush()
            market = Market(
                exchange_id=exchange.id,
                symbol="PTSTALEFILLUSD",
                base_asset="PTS",
                quote_asset="USD",
                market_type="perpetual",
            )
            session.add(market)
            await session.flush()
            open_time = datetime.now(UTC) - timedelta(hours=3)
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + timedelta(hours=1),
                    open=Decimal("500"),
                    high=Decimal("500"),
                    low=Decimal("500"),
                    close=Decimal("500"),
                    volume=Decimal("10"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
            await session.commit()

        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        order = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTSTALEFILLUSD", side="buy", quantity=Decimal("1")),
        )

        assert order.price_source == "candle_close"
        assert order.is_stale_price is True


@pytest.mark.asyncio
class TestBalanceAndPositionRejection:
    async def test_rejects_a_buy_that_would_take_the_balance_negative(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTPOORUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTPOORUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("500"))
        )

        with pytest.raises(InsufficientBalanceError):
            await service.place_order(
                uuid.UUID(account.id),
                PaperOrderRequest(symbol="PTPOORUSD", side="buy", quantity=Decimal("1")),
            )

        refreshed = await service.get_account(uuid.UUID(account.id))
        assert float(refreshed.balance) == pytest.approx(500.0)  # untouched, not partially filled
        positions = await service.list_positions(uuid.UUID(account.id))
        assert positions.positions == []

    async def test_rejects_a_sell_exceeding_the_held_quantity(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTSHORTUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTSHORTUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTSHORTUSD", side="buy", quantity=Decimal("1")),
        )

        with pytest.raises(InsufficientPositionError):
            await service.place_order(
                uuid.UUID(account.id),
                PaperOrderRequest(symbol="PTSHORTUSD", side="sell", quantity=Decimal("2")),
            )

    async def test_rejects_a_sell_with_no_position_at_all(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTNOPOSUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTNOPOSUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )

        with pytest.raises(InsufficientPositionError):
            await service.place_order(
                uuid.UUID(account.id),
                PaperOrderRequest(symbol="PTNOPOSUSD", side="sell", quantity=Decimal("1")),
            )

    async def test_raises_for_an_unknown_account(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory, MarketStateManager())
        with pytest.raises(PaperAccountNotFoundError):
            await service.get_account(uuid.uuid4())

    async def test_raises_for_an_unknown_market_symbol(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory, MarketStateManager())
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("1000"))
        )
        with pytest.raises(MarketNotFoundError):
            await service.place_order(
                uuid.UUID(account.id),
                PaperOrderRequest(symbol="DOES-NOT-EXIST", side="buy", quantity=Decimal("1")),
            )


@pytest.mark.asyncio
class TestHandComputedPnl:
    async def test_realized_and_unrealized_pnl_match_hand_computed_values(
        self, session_factory: SessionFactory
    ) -> None:
        """A fixture sequence with round numbers, computed by hand end to
        end:

        - start 100000; buy 10 @ 1000 -> fill 1000.5, notional 10005.0,
          fee 10.005, cost 10015.005, balance 89984.995, realized_pnl -10.005
          (the buy's own fee — the only thing a buy alone ever realizes).
        - mark-to-market at 1100 (no fill) -> unrealized_pnl
          (1100 - 1000.5) * 10 = 995.0.
        - sell 10 @ 1100 -> fill 1100 * (1 - 5/10000) = 1099.45,
          notional 10994.5, fee 10.9945, proceeds 10983.5055,
          balance 100968.5005, this trade's own realized_pnl
          (1099.45 - 1000.5) * 10 - 10.9945 = 978.5055, cumulative
          realized_pnl -10.005 + 978.5055 = 968.5005.
        - Once the position is fully closed, balance reconciles exactly
          against starting_balance + realized_pnl (100000 + 968.5005 =
          100968.5005) — see `PaperTradingService`'s own module docstring
          for why.
        """
        await seed_market(session_factory, symbol="PTPNLUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTPNLUSD", "1000")

        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )

        buy = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTPNLUSD", side="buy", quantity=Decimal("10")),
        )
        assert float(buy.fill_price) == pytest.approx(1000.5)
        assert buy.realized_pnl is None

        after_buy = await service.get_account(uuid.UUID(account.id))
        assert float(after_buy.balance) == pytest.approx(89984.995)
        assert float(after_buy.realized_pnl) == pytest.approx(-10.005)

        await publish_ticker(bus, "PTPNLUSD", "1100")
        positions = await service.list_positions(uuid.UUID(account.id))
        assert len(positions.positions) == 1
        position = positions.positions[0]
        assert float(position.quantity) == pytest.approx(10.0)
        assert float(position.average_entry_price) == pytest.approx(1000.5)
        assert float(position.unrealized_pnl) == pytest.approx(995.0)

        summary_before_sell = await service.summary(uuid.UUID(account.id))
        assert float(summary_before_sell.unrealized_pnl) == pytest.approx(995.0)
        assert float(summary_before_sell.realized_pnl) == pytest.approx(-10.005)
        assert float(summary_before_sell.total_equity) == pytest.approx(89984.995 + 1100 * 10)
        assert summary_before_sell.open_position_count == 1

        sell = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTPNLUSD", side="sell", quantity=Decimal("10")),
        )
        assert float(sell.fill_price) == pytest.approx(1099.45)
        assert sell.realized_pnl is not None
        assert float(sell.realized_pnl) == pytest.approx(978.5055)

        final_account = await service.get_account(uuid.UUID(account.id))
        assert float(final_account.balance) == pytest.approx(100968.5005)
        assert float(final_account.realized_pnl) == pytest.approx(968.5005)
        assert float(final_account.balance) == pytest.approx(
            100000.0 + float(final_account.realized_pnl)
        )

        final_positions = await service.list_positions(uuid.UUID(account.id))
        assert final_positions.positions == []  # fully closed — no longer "open"

        final_summary = await service.summary(uuid.UUID(account.id))
        assert float(final_summary.unrealized_pnl) == pytest.approx(0.0)
        assert final_summary.open_position_count == 0
        assert float(final_summary.total_equity) == pytest.approx(100968.5005)


@pytest.mark.asyncio
class TestAverageCostBasisAcrossMultipleBuys:
    async def test_average_entry_price_blends_two_buys_at_different_prices(
        self, session_factory: SessionFactory
    ) -> None:
        """A single buy can't distinguish "blended VWAP" from "first buy
        price" or "most recent buy price" — they're all identical when
        there's only one fill. This fixture buys the same symbol twice at
        two genuinely different prices, then sells part of the combined
        position, so `average_entry_price` and the sell's own realized PnL
        only come out right if the cost basis is a real quantity-weighted
        blend of both buys, not either one alone.

        Hand-computed, end to end:

        - buy 10 @ raw 1000 -> fill 1000 * 1.0005 = 1000.5, cost-basis
          units 10 * 1000.5 = 10005.0, fee 10005.0 * 0.001 = 10.005.
        - buy 10 @ raw 1200 -> fill 1200 * 1.0005 = 1200.6, cost-basis
          units 10 * 1200.6 = 12006.0, fee 12006.0 * 0.001 = 12.006.
        - blended average_entry_price = (10005.0 + 12006.0) / 20 =
          22011.0 / 20 = 1100.55 — *not* 1000.5 (first buy) and *not*
          1200.6 (most recent buy).
        - sell 5 @ raw 1300 -> fill 1300 * (1 - 0.0005) = 1299.35,
          notional 1299.35 * 5 = 6496.75, fee 6496.75 * 0.001 = 6.49675,
          this trade's own realized_pnl = (1299.35 - 1100.55) * 5 -
          6.49675 = 198.8 * 5 - 6.49675 = 994.0 - 6.49675 = 987.50325.
        - cumulative realized_pnl = -10.005 (buy 1's fee) - 12.006 (buy
          2's fee) + 987.50325 (the sell) = 965.49225.
        - the remaining position (15 units) keeps the *same* blended
          average_entry_price, 1100.55 — a sell never moves it; only a
          buy's own VWAP average ever does.
        """
        await seed_market(session_factory, symbol="PTBLENDUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )

        await publish_ticker(bus, "PTBLENDUSD", "1000")
        first_buy = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTBLENDUSD", side="buy", quantity=Decimal("10")),
        )
        assert float(first_buy.fill_price) == pytest.approx(1000.5)

        await publish_ticker(bus, "PTBLENDUSD", "1200")
        second_buy = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTBLENDUSD", side="buy", quantity=Decimal("10")),
        )
        assert float(second_buy.fill_price) == pytest.approx(1200.6)

        positions_after_buys = await service.list_positions(uuid.UUID(account.id))
        assert len(positions_after_buys.positions) == 1
        blended_position = positions_after_buys.positions[0]
        assert float(blended_position.quantity) == pytest.approx(20.0)
        # The actual proof: neither 1000.5 (first buy) nor 1200.6 (most
        # recent buy) alone — the real quantity-weighted blend of both.
        assert float(blended_position.average_entry_price) == pytest.approx(1100.55)

        await publish_ticker(bus, "PTBLENDUSD", "1300")
        sell = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTBLENDUSD", side="sell", quantity=Decimal("5")),
        )
        assert float(sell.fill_price) == pytest.approx(1299.35)
        assert sell.realized_pnl is not None
        assert float(sell.realized_pnl) == pytest.approx(987.50325)

        final_account = await service.get_account(uuid.UUID(account.id))
        assert float(final_account.realized_pnl) == pytest.approx(965.49225)

        remaining_positions = await service.list_positions(uuid.UUID(account.id))
        assert len(remaining_positions.positions) == 1
        remaining = remaining_positions.positions[0]
        assert float(remaining.quantity) == pytest.approx(15.0)
        # A sell never moves the cost basis — still the same blend as before.
        assert float(remaining.average_entry_price) == pytest.approx(1100.55)
