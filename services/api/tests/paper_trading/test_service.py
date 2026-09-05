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

import asyncio
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
    AccountUpdateConflictError,
    InsufficientBalanceError,
    InsufficientPositionError,
    InvalidStopLossPriceError,
    InvalidTakeProfitPriceError,
    MaxExposureExceededError,
    MaxPositionSizeExceededError,
    PaperAccountNotFoundError,
    PositionNotFoundError,
    StopLossNotBelowTakeProfitError,
    TradingHaltedError,
)
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperOrderRequest,
    PositionThresholdsUpdateRequest,
)
from app.services.market_query import MarketNotFoundError
from app.services.paper_trading import PaperTradingService
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory

SLIPPAGE_BPS = 5
FEE_BPS = 10
TRIGGERED_SLIPPAGE_BPS = 25
STALENESS_THRESHOLD = timedelta(seconds=300)
MAX_ORDER_ATTEMPTS = 5

#: `build_service`'s own default account risk limits are deliberately
#: wide open (100%) — every fixture in this file predates the pre-trade
#: risk limits feature and exercises fill/PnL/rejection arithmetic with
#: quantities chosen for *that*, not for staying under a 10%/50%/20%
#: ceiling (e.g. `TestHandComputedPnl`'s `buy 10 @ ~$1000` against a
#: $100,000 account is *itself* ~10.005% of balance once slippage is
#: applied — deliberately at the edge of a realistic limit, but that edge
#: is not what those tests are about). The risk-limit tests below
#: (`TestPositionSizeLimit` etc.) override these per account, explicitly,
#: with the platform's real default percentages — never relying on this
#: wide-open default.
GENEROUS_MAX_PCT = Decimal("100")


async def seed_market(session_factory: SessionFactory, *, symbol: str) -> None:
    async with session_factory() as session:
        exchange = Exchange(
            name=f"Delta Exchange {symbol}", slug=f"delta-{symbol.lower()}", country="India"
        )
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
        triggered_slippage_bps=TRIGGERED_SLIPPAGE_BPS,
        staleness_threshold=STALENESS_THRESHOLD,
        default_max_position_size_pct=GENEROUS_MAX_PCT,
        default_max_exposure_pct=GENEROUS_MAX_PCT,
        default_max_drawdown_pct=GENEROUS_MAX_PCT,
        max_order_attempts=MAX_ORDER_ATTEMPTS,
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


@pytest.mark.asyncio
class TestPositionSizeLimit:
    """`max_position_size_pct` isolated from the other two limits (both
    set wide open at account-creation time) so only the position-sizing
    check itself is under test."""

    async def test_rejects_an_order_whose_resulting_position_exceeds_the_limit(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTPOSLIMITUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTPOSLIMITUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=Decimal("10"),
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)

        # 11 units at a ~$1000.5 fill = ~$11,005.5 — 11.0055% of the
        # $100,000 balance, over the 10% limit.
        with pytest.raises(MaxPositionSizeExceededError):
            await service.place_order(
                account_id,
                PaperOrderRequest(symbol="PTPOSLIMITUSD", side="buy", quantity=Decimal("11")),
            )

        # Rejected outright, not partially filled.
        refreshed = await service.get_account(account_id)
        assert float(refreshed.balance) == pytest.approx(100000.0)
        positions = await service.list_positions(account_id)
        assert positions.positions == []

    async def test_an_order_just_under_the_limit_succeeds(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTPOSOKUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTPOSOKUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=Decimal("10"),
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )

        # 9 units at a ~$1000.5 fill = ~$9,004.5 — 9.0045% of balance,
        # comfortably under the 10% limit.
        order = await service.place_order(
            uuid.UUID(account.id),
            PaperOrderRequest(symbol="PTPOSOKUSD", side="buy", quantity=Decimal("9")),
        )
        assert float(order.fill_price) == pytest.approx(1000.5)


@pytest.mark.asyncio
class TestExposureLimit:
    """`max_exposure_pct` proven against *current*, not entry, prices: a
    position bought cheap that has since become far more valuable must
    count at its current value toward exposure — never its (now stale)
    cost basis — matching this task's own objective that risk math never
    runs on stale numbers."""

    async def test_rejects_an_order_once_a_held_positions_current_value_alone_breaches_exposure(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTEXPHELDUSD")
        await seed_market(session_factory, symbol="PTEXPNEWUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=Decimal("50"),
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)

        # Bought cheap: 1 unit at ~$100 — a negligible ~0.1% of balance
        # at cost. If exposure were (wrongly) valued at entry price, it
        # would never threaten a 50% limit.
        await publish_ticker(bus, "PTEXPHELDUSD", "100")
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="PTEXPHELDUSD", side="buy", quantity=Decimal("1")),
        )

        # The market moves hard: this same 1 unit is now worth $100,000 —
        # already over the entire account balance on its own.
        await publish_ticker(bus, "PTEXPHELDUSD", "100000")

        # A tiny, otherwise-trivial order in a *different* symbol should
        # still be rejected, because total exposure (this new order's own
        # negligible value + the held position's now-huge *current*
        # value) is what's checked — not the held position's original,
        # long-stale cost.
        await publish_ticker(bus, "PTEXPNEWUSD", "1")
        with pytest.raises(MaxExposureExceededError):
            await service.place_order(
                account_id,
                PaperOrderRequest(symbol="PTEXPNEWUSD", side="buy", quantity=Decimal("0.001")),
            )

        # The trivial order was rejected outright — never partially filled.
        positions = await service.list_positions(account_id)
        assert {p.symbol for p in positions.positions} == {"PTEXPHELDUSD"}


@pytest.mark.asyncio
class TestDrawdownHalt:
    """`max_drawdown_pct` — evaluated against the account's own cash
    `balance` after a trade completes (this feature's own spec), isolated
    from the other two limits (both wide open here)."""

    async def test_a_trade_that_breaches_drawdown_halts_the_account(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTDRAWDOWNUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTDRAWDOWNUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("10000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=Decimal("20"),
            )
        )
        account_id = uuid.UUID(account.id)

        # 2 units at a ~$1000.5 fill: notional $2001.0, fee $2.001, total
        # cost $2003.001 — new balance $7996.999, a 20.03% drop from the
        # $10,000 peak, just over the 20% drawdown limit. The order
        # itself is not blocked by its own resulting halt (the halt is
        # evaluated *after* this trade, per this feature's own spec).
        order = await service.place_order(
            account_id,
            PaperOrderRequest(symbol="PTDRAWDOWNUSD", side="buy", quantity=Decimal("2")),
        )
        assert float(order.fill_price) == pytest.approx(1000.5)

        halted_account = await service.get_account(account_id)
        assert halted_account.trading_halted is True
        assert float(halted_account.peak_balance) == pytest.approx(10000.0)

        # Any further order — even one that would otherwise be perfectly
        # fine — is rejected outright until explicitly resumed.
        with pytest.raises(TradingHaltedError):
            await service.place_order(
                account_id,
                PaperOrderRequest(symbol="PTDRAWDOWNUSD", side="buy", quantity=Decimal("0.001")),
            )

        # Still halted, still exactly the same balance — the rejected
        # attempt never touched anything.
        still_halted = await service.get_account(account_id)
        assert still_halted.trading_halted is True
        assert float(still_halted.balance) == pytest.approx(7996.999)


@pytest.mark.asyncio
class TestResumeTrading:
    """`resume_trading` is the *only* way a drawdown halt ever clears, and
    also resets `peak_balance` to the account's current balance (see that
    method's own docstring for why: without the reset, an account still
    deep in drawdown against its old peak would re-halt on its very next
    order regardless of that order's own direction)."""

    async def test_resume_clears_the_halt_and_a_valid_order_then_succeeds(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTRESUMEUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTRESUMEUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("10000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=Decimal("20"),
            )
        )
        account_id = uuid.UUID(account.id)

        # Same halt-inducing trade as `TestDrawdownHalt`.
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="PTRESUMEUSD", side="buy", quantity=Decimal("2")),
        )
        halted_account = await service.get_account(account_id)
        assert halted_account.trading_halted is True

        with pytest.raises(TradingHaltedError):
            await service.place_order(
                account_id,
                PaperOrderRequest(symbol="PTRESUMEUSD", side="buy", quantity=Decimal("0.001")),
            )

        resumed = await service.resume_trading(account_id)
        assert resumed.trading_halted is False
        # peak_balance resets to the current (post-halt) balance, not the
        # original $10,000 — otherwise the next order below would
        # immediately re-halt regardless of its own direction.
        assert float(resumed.peak_balance) == pytest.approx(7996.999)

        # A valid, small order now succeeds — the halt is genuinely
        # cleared, not merely bypassed for one call.
        order = await service.place_order(
            account_id,
            PaperOrderRequest(symbol="PTRESUMEUSD", side="buy", quantity=Decimal("0.001")),
        )
        assert order is not None

        final_account = await service.get_account(account_id)
        assert final_account.trading_halted is False


@pytest.mark.asyncio
class TestConcurrentExposureRace:
    """The concurrency guarantee this task exists to prove: two orders
    that would each individually pass the exposure check, placed via
    `asyncio.gather` — genuinely concurrently, not sequentially — must
    never both succeed when their combined effect would breach the
    limit. Mirrors `tests/training/test_service.py`'s own
    `test_two_genuinely_concurrent_starts_reject_exactly_one` shape: two
    independent service instances (each its own session), racing on the
    same account id."""

    async def test_two_concurrent_orders_that_would_jointly_breach_exposure_reject_exactly_one(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTRACEAUSD")
        await seed_market(session_factory, symbol="PTRACEBUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTRACEAUSD", "1000")
        await publish_ticker(bus, "PTRACEBUSD", "1000")

        creator = build_service(session_factory, state_manager)
        account = await creator.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=Decimal("50"),
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)

        # Two independent service instances — each its own session —
        # racing two *different* symbols' orders on the same account
        # concurrently, not one after the other. Each order alone
        # (~$30,015, ~30.015% of balance) is comfortably under the 50%
        # exposure limit; together (~60.03%) they are not.
        service_a = build_service(session_factory, state_manager)
        service_b = build_service(session_factory, state_manager)

        results = await asyncio.gather(
            service_a.place_order(
                account_id,
                PaperOrderRequest(symbol="PTRACEAUSD", side="buy", quantity=Decimal("30")),
            ),
            service_b.place_order(
                account_id,
                PaperOrderRequest(symbol="PTRACEBUSD", side="buy", quantity=Decimal("30")),
            ),
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]

        assert len(successes) == 1, f"expected exactly one winner, got: {results}"
        assert len(failures) == 1, f"expected exactly one rejection, got: {results}"
        # This is the assertion that distinguishes "the loser correctly
        # re-evaluated its own recomputed exposure check against the
        # winner's already-committed position and failed *that*" from
        # "the loser merely exhausted its optimistic-lock retries and
        # gave up for an unrelated reason" — the two calls race only
        # once (a two-way race), so the loser's very first retry already
        # sees a stable, winner-committed account/position state and
        # must resolve definitively there; it should never come anywhere
        # near exhausting `max_order_attempts` (5) in a genuine two-way
        # race. `MaxExposureExceededError` is the *only* acceptable
        # failure type here — explicitly not `AccountUpdateConflictError`
        # (retry exhaustion), which `TestConcurrencyGuardExhaustion`
        # below proves is a real, distinct, reachable outcome under a
        # *different* condition (every attempt losing the optimistic
        # lock, not a recomputed risk check failing) — so this isinstance
        # check is not vacuous.
        assert not isinstance(failures[0], AccountUpdateConflictError), (
            f"the loser must fail because its recomputed exposure check rejected it, not "
            f"because it ran out of retries against the winner's committed state: {failures[0]!r}"
        )
        assert isinstance(failures[0], MaxExposureExceededError), (
            f"the loser must be rejected for breaching exposure once it sees the winner's "
            f"already-committed position, not fail some other way: {failures[0]!r}"
        )

        # The database agrees: only the winner's position was ever created,
        # and its value alone (~$30,015) proves the winner's own atomic
        # UPDATE actually committed — this isn't "both failed silently."
        positions = await creator.list_positions(account_id)
        assert len(positions.positions) == 1
        assert float(positions.positions[0].quantity) == pytest.approx(30.0)


@pytest.mark.asyncio
class TestConcurrencyGuardExhaustion:
    """The *other* branch of `place_order`'s retry loop — distinct from
    `TestConcurrentExposureRace` above, which never exhausts a single
    attempt (the loser's recomputed risk check rejects it on its very
    first retry). This class forces every attempt's atomic `UPDATE` to
    report a lost race — not just one — so the loop actually runs out of
    `max_order_attempts` and falls through to the explicit
    `raise AccountUpdateConflictError(...)` at the bottom of
    `place_order`, proving that path is a deliberate, typed, 409
    rejection — never a silent fallthrough, an unhandled exception, or a
    bypass of the checks above it."""

    async def test_exhausting_every_retry_raises_a_specific_conflict_error(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTCONFLICTUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTCONFLICTUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)

        call_count = 0

        async def always_lose_the_race(*args: object, **kwargs: object) -> None:
            """Stands in for `PaperAccountRepository.try_apply_trade_effects`
            and reports "someone else changed the account since you read
            it" (a `None` return) unconditionally — the exact situation
            two concurrent orders produce for the loser's *first* retry,
            forced here to happen on *every* attempt instead of just one."""
            nonlocal call_count
            call_count += 1
            return None

        # Replace only this one method on this one instance — an
        # instance attribute assignment bypasses the descriptor
        # protocol, so `always_lose_the_race` is called exactly as
        # written (no implicit `self`), receiving whatever positional/
        # keyword arguments `place_order` passes.
        service.account_repository.try_apply_trade_effects = always_lose_the_race

        with pytest.raises(AccountUpdateConflictError) as exc_info:
            await service.place_order(
                account_id,
                PaperOrderRequest(symbol="PTCONFLICTUSD", side="buy", quantity=Decimal("1")),
            )

        # Every configured attempt was actually made — the loop did not
        # bail early, retry a different number of times, or skip work.
        assert call_count == MAX_ORDER_ATTEMPTS
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "account_update_conflict"
        assert str(MAX_ORDER_ATTEMPTS) in exc_info.value.message

        # Nothing was silently applied and the halted/position-size/
        # exposure checks were never bypassed: the account is untouched,
        # and no position or order exists.
        untouched = await service.get_account(account_id)
        assert float(untouched.balance) == pytest.approx(100000.0)
        assert untouched.trading_halted is False
        positions = await service.list_positions(account_id)
        assert positions.positions == []
        orders = await service.list_orders(
            account_id, sort="created_at", direction="desc", limit=10, offset=0
        )
        assert orders.total == 0


@pytest.mark.asyncio
class TestStopLossTakeProfitValidation:
    """Set-time validation — `PaperTradingService._validate_thresholds`,
    exercised through both entry points: a buy order's own optional
    `stop_loss_price`/`take_profit_price`, and the dedicated
    `update_position_thresholds` endpoint. The monitor that actually
    *acts* on these once set is covered separately in
    `tests/paper_trading/test_monitor.py`."""

    async def test_a_stop_loss_at_or_above_the_current_price_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTVALSLUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTVALSLUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)

        # Exactly at the current price — would trigger immediately.
        with pytest.raises(InvalidStopLossPriceError):
            await service.place_order(
                account_id,
                PaperOrderRequest(
                    symbol="PTVALSLUSD",
                    side="buy",
                    quantity=Decimal("1"),
                    stop_loss_price=Decimal("1000"),
                ),
            )

        # Rejected outright — no order, no position, nothing partially applied.
        positions = await service.list_positions(account_id)
        assert positions.positions == []
        orders = await service.list_orders(
            account_id, sort="created_at", direction="desc", limit=10, offset=0
        )
        assert orders.total == 0

    async def test_a_take_profit_at_or_below_the_current_price_is_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTVALTPUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTVALTPUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)

        with pytest.raises(InvalidTakeProfitPriceError):
            await service.place_order(
                account_id,
                PaperOrderRequest(
                    symbol="PTVALTPUSD",
                    side="buy",
                    quantity=Decimal("1"),
                    take_profit_price=Decimal("1000"),
                ),
            )

    async def test_a_sell_can_never_carry_thresholds(self) -> None:
        with pytest.raises(ValueError, match="only apply to a buy"):
            PaperOrderRequest(
                symbol="PTVALSELLUSD",
                side="sell",
                quantity=Decimal("1"),
                stop_loss_price=Decimal("900"),
            )

    async def test_valid_thresholds_are_set_at_order_open_time(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTVALOKUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTVALOKUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTVALOKUSD",
                side="buy",
                quantity=Decimal("1"),
                stop_loss_price=Decimal("900"),
                take_profit_price=Decimal("1100"),
            ),
        )

        positions = await service.list_positions(account_id)
        assert len(positions.positions) == 1
        position = positions.positions[0]
        assert float(position.stop_loss_price) == pytest.approx(900.0)
        assert float(position.take_profit_price) == pytest.approx(1100.0)

    async def test_a_later_buy_that_omits_thresholds_never_clears_an_existing_one(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTVALKEEPUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTVALKEEPUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTVALKEEPUSD",
                side="buy",
                quantity=Decimal("1"),
                stop_loss_price=Decimal("900"),
            ),
        )

        # A second buy of the same symbol, mentioning neither threshold.
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="PTVALKEEPUSD", side="buy", quantity=Decimal("1")),
        )

        positions = await service.list_positions(account_id)
        assert len(positions.positions) == 1
        assert float(positions.positions[0].stop_loss_price) == pytest.approx(900.0)

    async def test_stop_loss_and_take_profit_set_at_two_different_prices_are_cross_validated(
        self, session_factory: SessionFactory
    ) -> None:
        """Each threshold is independently valid against *its own*
        current price at the moment it's set — that alone doesn't stop a
        high stop-loss and a low take-profit being set at two different
        times as the price moves between them. This proves the cross-
        check (`stop_loss_price < take_profit_price`) catches exactly
        that gap: a take-profit set first while price is low, then a
        stop-loss set later while price is high enough to individually
        validate but that ends up numerically above the earlier
        take-profit."""
        await seed_market(session_factory, symbol="PTVALCROSSUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(
                starting_balance=Decimal("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)

        # Take-profit set first, while price is 1000 — 1100 is valid (above 1000).
        await publish_ticker(bus, "PTVALCROSSUSD", "1000")
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTVALCROSSUSD",
                side="buy",
                quantity=Decimal("1"),
                take_profit_price=Decimal("1100"),
            ),
        )

        # Price rises; a stop-loss of 1150 is individually valid against
        # the *new* current price (1200) but is >= the earlier take-profit (1100).
        await publish_ticker(bus, "PTVALCROSSUSD", "1200")
        with pytest.raises(StopLossNotBelowTakeProfitError):
            await service.update_position_thresholds(
                account_id,
                "PTVALCROSSUSD",
                PositionThresholdsUpdateRequest(stop_loss_price=Decimal("1150")),
            )

        # The existing, valid take-profit is untouched by the rejected attempt.
        positions = await service.list_positions(account_id)
        assert float(positions.positions[0].take_profit_price) == pytest.approx(1100.0)
        assert positions.positions[0].stop_loss_price is None


@pytest.mark.asyncio
class TestUpdatePositionThresholds:
    """`update_position_thresholds` — the dedicated set/update/clear
    endpoint, independent of placing any order."""

    async def test_sets_both_thresholds_on_an_existing_position(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTUPDATESETUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTUPDATESETUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(symbol="PTUPDATESETUSD", side="buy", quantity=Decimal("1")),
        )

        updated = await service.update_position_thresholds(
            account_id,
            "PTUPDATESETUSD",
            PositionThresholdsUpdateRequest(
                stop_loss_price=Decimal("900"), take_profit_price=Decimal("1100")
            ),
        )
        assert float(updated.stop_loss_price) == pytest.approx(900.0)
        assert float(updated.take_profit_price) == pytest.approx(1100.0)

    async def test_omitting_a_field_leaves_it_unchanged(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTUPDATEKEEPUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTUPDATEKEEPUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTUPDATEKEEPUSD",
                side="buy",
                quantity=Decimal("1"),
                stop_loss_price=Decimal("900"),
                take_profit_price=Decimal("1100"),
            ),
        )

        # Only stop_loss_price is named — take_profit_price is *omitted*,
        # not sent as null, so it must survive untouched.
        updated = await service.update_position_thresholds(
            account_id,
            "PTUPDATEKEEPUSD",
            PositionThresholdsUpdateRequest(stop_loss_price=Decimal("950")),
        )
        assert float(updated.stop_loss_price) == pytest.approx(950.0)
        assert float(updated.take_profit_price) == pytest.approx(1100.0)

    async def test_an_explicit_null_clears_a_threshold(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTUPDATECLEARUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PTUPDATECLEARUSD", "1000")
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)
        await service.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PTUPDATECLEARUSD",
                side="buy",
                quantity=Decimal("1"),
                stop_loss_price=Decimal("900"),
                take_profit_price=Decimal("1100"),
            ),
        )

        # stop_loss_price explicitly null — cleared, not left unchanged;
        # take_profit_price omitted — untouched.
        updated = await service.update_position_thresholds(
            account_id,
            "PTUPDATECLEARUSD",
            PositionThresholdsUpdateRequest(stop_loss_price=None),
        )
        assert updated.stop_loss_price is None
        assert float(updated.take_profit_price) == pytest.approx(1100.0)

    async def test_raises_for_an_account_with_no_open_position_in_this_symbol(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_market(session_factory, symbol="PTUPDATENOPOSUSD")
        state_manager = MarketStateManager()
        service = build_service(session_factory, state_manager)
        account = await service.create_account(
            PaperAccountCreateRequest(starting_balance=Decimal("100000"))
        )
        account_id = uuid.UUID(account.id)

        with pytest.raises(PositionNotFoundError):
            await service.update_position_thresholds(
                account_id,
                "PTUPDATENOPOSUSD",
                PositionThresholdsUpdateRequest(stop_loss_price=Decimal("900")),
            )
