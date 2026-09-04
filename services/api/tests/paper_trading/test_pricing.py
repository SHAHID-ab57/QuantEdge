"""Unit tests for `app.paper_trading.pricing` — price resolution precedence
(ticker, then trade, then a fallback candle), staleness marking, and the
slippage/fee execution model. Realistic execution is the one thing this
feature exists to guarantee, so every one of these is a direct, numeric
proof, not an assertion in prose.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.events.bus import EventBus
from app.marketdata.bus_events import TickerUpdated, TradeEventReceived
from app.marketdata.models import TickerEvent, TradeEvent
from app.models.candle import Candle
from app.models.exchange import Exchange
from app.models.market import Market
from app.paper_trading.base import FillQuote
from app.paper_trading.errors import NoPriceAvailableError
from app.paper_trading.pricing import apply_fill_model, resolve_current_price
from app.repositories.candles import CandleRepository
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory

STALENESS_THRESHOLD = timedelta(seconds=300)


async def seed_market_with_candle(
    session_factory: SessionFactory, *, symbol: str, close: str, open_time: datetime
) -> uuid.UUID:
    """A market with exactly one real stored 1h candle — the fallback path's own data."""
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug=f"delta-{symbol.lower()}", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="perpetual",
        )
        session.add(market)
        await session.flush()
        session.add(
            Candle(
                market_id=market.id,
                timeframe="1h",
                open_time=open_time,
                close_time=open_time + timedelta(hours=1),
                open=Decimal(close),
                high=Decimal(close),
                low=Decimal(close),
                close=Decimal(close),
                volume=Decimal("100"),
                quote_volume=None,
                trade_count=None,
                source="delta",
            )
        )
        await session.commit()
        return market.id


async def seed_empty_market(session_factory: SessionFactory, *, symbol: str) -> uuid.UUID:
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug=f"delta-{symbol.lower()}", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()
        return market.id


@pytest.mark.asyncio
class TestResolveCurrentPrice:
    async def test_prefers_a_live_ticker_over_everything_else(
        self, session_factory: SessionFactory
    ) -> None:
        market_id = await seed_market_with_candle(
            session_factory,
            symbol="PTICKERUSD",
            close="100",
            open_time=datetime.now(UTC) - timedelta(hours=1),
        )
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await bus.publish(
            TickerUpdated(
                source="test",
                ticker=TickerEvent(
                    exchange="delta",
                    symbol="PTICKERUSD",
                    event_time=datetime.now(UTC),
                    last_price=Decimal("200"),
                ),
            )
        )
        await bus.drain()

        quote = await resolve_current_price(
            state_manager=state_manager,
            candle_repository=CandleRepository(session_factory()),
            market_id=market_id,
            symbol="PTICKERUSD",
            staleness_threshold=STALENESS_THRESHOLD,
        )

        assert quote.price == Decimal("200")
        assert quote.source == "ticker"
        assert quote.is_stale is False

    async def test_falls_back_to_trade_when_no_ticker_is_present(
        self, session_factory: SessionFactory
    ) -> None:
        market_id = await seed_market_with_candle(
            session_factory,
            symbol="PTRADEUSD",
            close="100",
            open_time=datetime.now(UTC) - timedelta(hours=1),
        )
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await bus.publish(
            TradeEventReceived(
                source="test",
                trade=TradeEvent(
                    exchange="delta",
                    symbol="PTRADEUSD",
                    side="buy",
                    price=Decimal("150"),
                    size=Decimal("1"),
                    event_time=datetime.now(UTC),
                ),
            )
        )
        await bus.drain()

        quote = await resolve_current_price(
            state_manager=state_manager,
            candle_repository=CandleRepository(session_factory()),
            market_id=market_id,
            symbol="PTRADEUSD",
            staleness_threshold=STALENESS_THRESHOLD,
        )

        assert quote.price == Decimal("150")
        assert quote.source == "trade"
        assert quote.is_stale is False

    async def test_falls_back_to_the_latest_stored_candle_close_when_no_live_data_flows(
        self, session_factory: SessionFactory
    ) -> None:
        """No live data at all (`market_data_live=false` — the exact
        situation of this dev environment right now) — the fallback is the
        real, recorded close of the latest candle."""
        market_id = await seed_market_with_candle(
            session_factory,
            symbol="PCANDLEUSD",
            close="123.45",
            open_time=datetime.now(UTC) - timedelta(minutes=2),
        )
        state_manager = MarketStateManager()

        quote = await resolve_current_price(
            state_manager=state_manager,
            candle_repository=CandleRepository(session_factory()),
            market_id=market_id,
            symbol="PCANDLEUSD",
            staleness_threshold=STALENESS_THRESHOLD,
        )

        # The in-memory SQLite test engine stores NUMERIC via REAL affinity
        # (no arbitrary-precision decimal storage), the same reason this
        # platform's own target generators (`app/ml_datasets/targets/`)
        # always compare a candle's own close via `float(...)`, never exact
        # `Decimal` equality, once it has round-tripped through storage.
        assert float(quote.price) == pytest.approx(123.45)
        assert quote.source == "candle_close"
        assert quote.is_stale is False  # 2 minutes old, well within the 300s threshold

    async def test_marks_a_fallback_price_stale_once_older_than_the_threshold(
        self, session_factory: SessionFactory
    ) -> None:
        market_id = await seed_market_with_candle(
            session_factory,
            symbol="PSTALEUSD",
            close="50",
            open_time=datetime.now(UTC) - timedelta(hours=2),
        )
        state_manager = MarketStateManager()

        quote = await resolve_current_price(
            state_manager=state_manager,
            candle_repository=CandleRepository(session_factory()),
            market_id=market_id,
            symbol="PSTALEUSD",
            staleness_threshold=STALENESS_THRESHOLD,
        )

        assert quote.source == "candle_close"
        assert quote.is_stale is True

    async def test_raises_when_nothing_is_available_at_all(
        self, session_factory: SessionFactory
    ) -> None:
        market_id = await seed_empty_market(session_factory, symbol="PEMPTYUSD")
        state_manager = MarketStateManager()

        with pytest.raises(NoPriceAvailableError):
            await resolve_current_price(
                state_manager=state_manager,
                candle_repository=CandleRepository(session_factory()),
                market_id=market_id,
                symbol="PEMPTYUSD",
                staleness_threshold=STALENESS_THRESHOLD,
            )


class TestApplyFillModel:
    """Slippage always moves the fill *against* the trader; the fee is
    always a cost on the fill's own notional — both computed exactly from
    the configured basis points, proven with round numbers that make the
    arithmetic independently checkable."""

    def _quote(self, price: str) -> FillQuote:
        return FillQuote(
            price=Decimal(price),
            source="candle_close",
            observed_at=datetime.now(UTC),
            is_stale=False,
        )

    def test_a_buy_fills_higher_than_the_quote_by_exactly_the_modeled_slippage(self) -> None:
        result = apply_fill_model(
            self._quote("1000"), side="buy", quantity=Decimal("10"), slippage_bps=5, fee_bps=10
        )

        assert result.fill_price == Decimal("1000.5")  # 1000 * (1 + 5/10000)
        assert result.slippage_applied == Decimal("0.5")
        assert result.notional == Decimal("10005.0")  # 1000.5 * 10
        assert result.fee_applied == Decimal("10.005")  # 10005.0 * 10/10000

    def test_a_sell_fills_lower_than_the_quote_by_exactly_the_modeled_slippage(self) -> None:
        result = apply_fill_model(
            self._quote("1000"), side="sell", quantity=Decimal("10"), slippage_bps=5, fee_bps=10
        )

        assert result.fill_price == Decimal("999.5")  # 1000 * (1 - 5/10000)
        assert result.slippage_applied == Decimal("0.5")
        assert result.notional == Decimal("9995.0")
        assert result.fee_applied == Decimal("9.995")

    def test_doubling_slippage_bps_alone_doubles_the_applied_slippage_exactly(self) -> None:
        """Proves the model actually reads the given setting, not a
        hardcoded constant. Held separately from fee_bps: slippage_applied
        is a pure linear function of slippage_bps for a fixed quote, but
        fee_applied is not (it is charged on *notional*, which already
        embeds slippage) — so the two settings are proven independently,
        never through a combined change that would conflate them."""
        base = apply_fill_model(
            self._quote("1000"), side="buy", quantity=Decimal("1"), slippage_bps=5, fee_bps=10
        )
        doubled = apply_fill_model(
            self._quote("1000"), side="buy", quantity=Decimal("1"), slippage_bps=10, fee_bps=10
        )

        assert doubled.slippage_applied == base.slippage_applied * 2
        assert doubled.fee_applied != base.fee_applied  # notional shifted too — expected

    def test_doubling_fee_bps_alone_doubles_the_applied_fee_exactly(self) -> None:
        base = apply_fill_model(
            self._quote("1000"), side="buy", quantity=Decimal("1"), slippage_bps=5, fee_bps=10
        )
        doubled = apply_fill_model(
            self._quote("1000"), side="buy", quantity=Decimal("1"), slippage_bps=5, fee_bps=20
        )

        assert doubled.fee_applied == base.fee_applied * 2
        assert doubled.slippage_applied == base.slippage_applied  # unaffected by fee_bps
