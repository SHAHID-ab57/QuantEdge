"""Stop-loss/take-profit monitor — the same event-bus subscriber pattern
`app.state.manager.MarketStateManager` uses (`bus.subscribe(event_type,
handler)`, an `isinstance` check narrowing each event), applied to
closing a position automatically the instant its stop-loss or
take-profit price is crossed.

**Why the event bus, not a new polling loop.** Every live price this
platform ever sees already flows through `EventBus` as a
`TickerUpdated`/`TradeEventReceived` event — the identical two types
`MarketStateManager.attach` subscribes to. A polling loop checking prices
on a timer would be a slower, redundant path to data this bus already
delivers the instant it changes; there is nothing for it to poll that
this monitor doesn't already get pushed to it directly.

**Why the event's own price, not `MarketStateManager`'s cached state.**
`EventBus.publish` schedules one `asyncio.Task` per subscriber
concurrently (`self._pending.add(asyncio.create_task(...))`) with no
ordering guarantee between them — this monitor's own handler and
`MarketStateManager`'s handler can run in either order for the *same*
event, so this monitor cannot assume `state_manager.get_latest_ticker`
already reflects the event that just fired it. It doesn't need to: the
event itself already carries the freshest possible price, so every
trigger check and the resulting fill both price directly from the event,
never a second, possibly-stale lookup through the state manager.

**Its own database session per event, never a request-scoped one.**
Mirrors `app.services.grading_scheduler.PredictionGradingScheduler`'s own
`get_engine()`-gated pattern exactly: there is no HTTP request behind a
bus event, so a fresh session is opened per relevant price event and
closed immediately after. `get_engine() is None` (database not
configured — the default in this test suite, see
`tests/conftest.py`) is a silent no-op, the same graceful-without-a-
database posture every other DB-optional component on this platform
already takes. Tests exercise this by monkeypatching this module's own
`get_engine` reference to the test's in-memory engine — the identical
technique `tests/services/test_grading_scheduler.py` already established.

**The "one tick crosses both levels" question, answered.**
`PaperTradingService._validate_thresholds` enforces, at set-time, that
`stop_loss_price` is strictly below `take_profit_price` whenever both are
set (in addition to each being independently valid against the current
price). That makes `price <= stop_loss_price` and
`price >= take_profit_price` mutually exclusive for *every* price,
structurally, by construction — not a runtime tie-break, and not
something that can be reached through the ordinary API surface. The
check order below (stop-loss first) is kept anyway, as defense-in-depth
for the case that invariant is ever violated some other way (a direct DB
write, a future bug): treating downside protection as the
higher-priority signal is the more conservative failure mode when a row
is ever actually inconsistent. A **gap** — a single tick landing far
past a threshold rather than exactly on it — still triggers correctly
(the check is `<=`/`>=`, never an exact-match `==`), and the resulting
fill prices at the *current*, post-gap price (with the wider triggered-
slippage model applied on top), never at the stale threshold price
itself — exactly how a real stop order behaves during a fast move.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.engine import get_engine
from app.events.bus import EventBus
from app.events.event import Event
from app.marketdata.bus_events import TickerUpdated, TradeEventReceived
from app.models.paper_trading import PaperPosition
from app.paper_trading.base import FillQuote
from app.paper_trading.pricing import is_stale
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)
from app.services.paper_trading import PaperTradingService
from app.state.manager import MarketStateManager

logger = logging.getLogger("app.paper_trading.monitor")


class StopLossTakeProfitMonitor:
    """Closes an open position automatically — through
    `PaperTradingService.trigger_close`, the same fill model and atomic
    concurrency guard a manual close uses — the instant a live price
    event crosses its stop-loss or take-profit."""

    def __init__(
        self,
        *,
        state_manager: MarketStateManager,
        slippage_bps: int,
        fee_bps: int,
        triggered_slippage_bps: int,
        staleness_threshold: timedelta,
        default_max_position_size_pct: Decimal,
        default_max_exposure_pct: Decimal,
        default_max_drawdown_pct: Decimal,
        max_order_attempts: int,
    ) -> None:
        self._state_manager = state_manager
        self._slippage_bps = slippage_bps
        self._fee_bps = fee_bps
        self._triggered_slippage_bps = triggered_slippage_bps
        self._staleness_threshold = staleness_threshold
        self._default_max_position_size_pct = default_max_position_size_pct
        self._default_max_exposure_pct = default_max_exposure_pct
        self._default_max_drawdown_pct = default_max_drawdown_pct
        self._max_order_attempts = max_order_attempts

    def attach(self, bus: EventBus) -> "StopLossTakeProfitMonitor":
        """Subscribe to the same two live-price event types
        `MarketStateManager` already watches."""
        bus.subscribe("TickerUpdated", self._on_ticker_updated)
        bus.subscribe("TradeEventReceived", self._on_trade_received)
        return self

    async def _on_ticker_updated(self, event: Event) -> None:
        if not isinstance(event, TickerUpdated):
            return
        ticker = event.ticker
        if ticker.last_price is None:
            return
        quote = FillQuote(
            price=ticker.last_price,
            source="ticker",
            observed_at=ticker.event_time,
            is_stale=is_stale(ticker.event_time, self._staleness_threshold),
        )
        await self._check_symbol(ticker.symbol, quote)

    async def _on_trade_received(self, event: Event) -> None:
        if not isinstance(event, TradeEventReceived):
            return
        trade = event.trade
        quote = FillQuote(
            price=trade.price,
            source="trade",
            observed_at=trade.event_time,
            is_stale=is_stale(trade.event_time, self._staleness_threshold),
        )
        await self._check_symbol(trade.symbol, quote)

    async def _check_symbol(self, symbol: str, quote: FillQuote) -> None:
        """Close every open position in `symbol`, across every account,
        whose stop-loss or take-profit this `quote` has crossed."""
        engine = get_engine()
        if engine is None:
            return

        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            position_repository = PaperPositionRepository(session)
            positions = await position_repository.list_open_with_thresholds(symbol)
            if not positions:
                return

            service = PaperTradingService(
                account_repository=PaperAccountRepository(session),
                order_repository=PaperOrderRepository(session),
                position_repository=position_repository,
                market_repository=MarketRepository(session),
                candle_repository=CandleRepository(session),
                state_manager=self._state_manager,
                slippage_bps=self._slippage_bps,
                fee_bps=self._fee_bps,
                triggered_slippage_bps=self._triggered_slippage_bps,
                staleness_threshold=self._staleness_threshold,
                default_max_position_size_pct=self._default_max_position_size_pct,
                default_max_exposure_pct=self._default_max_exposure_pct,
                default_max_drawdown_pct=self._default_max_drawdown_pct,
                max_order_attempts=self._max_order_attempts,
            )

            for position in positions:
                reason = self._crossed_threshold(position, quote.price)
                if reason is None:
                    continue
                try:
                    await service.trigger_close(
                        position.account_id, symbol, reason=reason, quote=quote
                    )
                except Exception:
                    # Isolated per position — one account's failure (or a
                    # lost concurrency race) must never stop this same
                    # price event from being checked against every other
                    # account's own position in this symbol.
                    logger.exception(
                        "Stop-loss/take-profit trigger failed: account=%s symbol=%s reason=%s",
                        position.account_id,
                        symbol,
                        reason,
                    )

    @staticmethod
    def _crossed_threshold(position: PaperPosition, price: Decimal) -> str | None:
        """`'stop_loss'`/`'take_profit'` if `price` has crossed that
        position's own threshold, else `None`. Stop-loss is checked
        first — see this module's own docstring for why that ordering is
        defense-in-depth, not something ordinary use can ever reach."""
        if position.stop_loss_price is not None and price <= Decimal(position.stop_loss_price):
            return "stop_loss"
        if position.take_profit_price is not None and price >= Decimal(position.take_profit_price):
            return "take_profit"
        return None
