"""Stop-loss/take-profit/liquidation monitor — the same event-bus subscriber
pattern `app.state.manager.MarketStateManager` uses (`bus.subscribe(event_type,
handler)`, an `isinstance` check narrowing each event), applied to
closing a position automatically the instant its stop-loss, take-profit or
liquidation price is crossed.

**Three triggers, checked in a fixed order: liquidation, then stop-loss,
then take-profit.** A stop and a take-profit are orders the simulator
executes on the *last* traded price; a liquidation is the exchange acting on
the account regardless of what the account intended, and it runs on the
*mark* price (Delta: "A position goes into liquidation when Mark Price
reaches the Liquidation Price"). Because the two use different prices a fast
move can cross both on one tick; liquidation is checked first because it is
the outcome the real venue would impose. It is only evaluated on a ticker
event, the one event that carries a mark price; if a ticker arrives without
one the last price stands in and the resulting order records
`trigger_price_basis='last_fallback'`. A trade event never triggers a
liquidation (it has no mark price to judge by).

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
from app.paper_trading.margin import is_liquidated
from app.paper_trading.pricing import is_stale
from app.repositories.audit_log import AuditLogRepository
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
    PaperStrategyDecisionRepository,
)
from app.repositories.training import TrainingJobRepository
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
        default_strategy_confidence_threshold_pct: Decimal,
        default_strategy_default_stop_loss_pct: Decimal,
        default_max_leverage: Decimal = Decimal("5"),
        maintenance_margin_rate: Decimal = Decimal("0.0025"),
        max_leverage_notional: Decimal = Decimal("100000"),
    ) -> None:
        self._default_max_leverage = default_max_leverage
        self._maintenance_margin_rate = maintenance_margin_rate
        self._max_leverage_notional = max_leverage_notional
        self._state_manager = state_manager
        self._slippage_bps = slippage_bps
        self._fee_bps = fee_bps
        self._triggered_slippage_bps = triggered_slippage_bps
        self._staleness_threshold = staleness_threshold
        self._default_max_position_size_pct = default_max_position_size_pct
        self._default_max_exposure_pct = default_max_exposure_pct
        self._default_max_drawdown_pct = default_max_drawdown_pct
        self._max_order_attempts = max_order_attempts
        self._default_strategy_confidence_threshold_pct = default_strategy_confidence_threshold_pct
        self._default_strategy_default_stop_loss_pct = default_strategy_default_stop_loss_pct

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
        stale = is_stale(ticker.event_time, self._staleness_threshold)
        last_quote = (
            FillQuote(
                price=ticker.last_price,
                source="ticker",
                observed_at=ticker.event_time,
                is_stale=stale,
            )
            if ticker.last_price is not None
            else None
        )
        # Liquidation runs on the mark price; the last price stands in only
        # when the ticker carries no mark, and the order says so.
        mark_price = ticker.mark_price if ticker.mark_price is not None else ticker.last_price
        if mark_price is None:
            return
        mark_quote = FillQuote(
            price=mark_price, source="ticker", observed_at=ticker.event_time, is_stale=stale
        )
        mark_basis = "mark" if ticker.mark_price is not None else "last_fallback"
        await self._check_symbol(
            ticker.symbol, last_quote, mark_quote=mark_quote, mark_basis=mark_basis
        )

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

    async def _check_symbol(
        self,
        symbol: str,
        quote: FillQuote | None,
        *,
        mark_quote: FillQuote | None = None,
        mark_basis: str = "mark",
    ) -> None:
        """Close every open position in `symbol`, across every account, that
        this event has liquidated (`mark_quote` crossed its liquidation
        price) or whose stop-loss/take-profit `quote` (the last price) has
        crossed — liquidation first, and never both for one position."""
        engine = get_engine()
        if engine is None:
            return

        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            position_repository = PaperPositionRepository(session)
            positions = await position_repository.list_open_monitored(symbol)
            if not positions:
                return

            service = PaperTradingService(
                account_repository=PaperAccountRepository(session),
                order_repository=PaperOrderRepository(session),
                position_repository=position_repository,
                market_repository=MarketRepository(session),
                candle_repository=CandleRepository(session),
                training_job_repository=TrainingJobRepository(session),
                strategy_decision_repository=PaperStrategyDecisionRepository(session),
                audit_log_repository=AuditLogRepository(session),
                state_manager=self._state_manager,
                slippage_bps=self._slippage_bps,
                fee_bps=self._fee_bps,
                triggered_slippage_bps=self._triggered_slippage_bps,
                staleness_threshold=self._staleness_threshold,
                default_max_position_size_pct=self._default_max_position_size_pct,
                default_max_exposure_pct=self._default_max_exposure_pct,
                default_max_drawdown_pct=self._default_max_drawdown_pct,
                max_order_attempts=self._max_order_attempts,
                default_strategy_confidence_threshold_pct=(
                    self._default_strategy_confidence_threshold_pct
                ),
                default_strategy_default_stop_loss_pct=(
                    self._default_strategy_default_stop_loss_pct
                ),
                default_max_leverage=self._default_max_leverage,
                maintenance_margin_rate=self._maintenance_margin_rate,
                max_leverage_notional=self._max_leverage_notional,
            )

            for position in positions:
                trigger_quote: FillQuote | None = None
                price_basis: str | None = None
                reason: str | None = None
                if mark_quote is not None and is_liquidated(
                    side=position.side,  # type: ignore[arg-type]
                    mark_price=mark_quote.price,
                    liquidation=(
                        Decimal(position.liquidation_price)
                        if position.liquidation_price is not None
                        else None
                    ),
                ):
                    reason, trigger_quote, price_basis = "liquidation", mark_quote, mark_basis
                elif quote is not None:
                    reason = self._crossed_threshold(position, quote.price)
                    trigger_quote = quote
                if reason is None or trigger_quote is None:
                    continue
                try:
                    await service.trigger_close(
                        position.account_id,
                        symbol,
                        reason=reason,
                        quote=trigger_quote,
                        price_basis=price_basis,
                    )
                except Exception:
                    # Isolated per position — one account's failure (or a
                    # lost concurrency race) must never stop this same
                    # price event from being checked against every other
                    # account's own position in this symbol.
                    logger.exception(
                        "Stop-loss/take-profit/liquidation trigger failed: "
                        "account=%s symbol=%s reason=%s",
                        position.account_id,
                        symbol,
                        reason,
                    )

    @staticmethod
    def _crossed_threshold(position: PaperPosition, price: Decimal) -> str | None:
        """`'stop_loss'`/`'take_profit'` if `price` has crossed that
        position's own threshold, else `None`. Direction depends on the
        side: a long's stop-loss is crossed at or below its price and its
        take-profit at or above; a short's are the reverse. Stop-loss is
        checked first — see this module's own docstring for why that
        ordering is defense-in-depth, not something ordinary use can ever
        reach."""
        stop = position.stop_loss_price
        take = position.take_profit_price
        if position.side == "short":
            if stop is not None and price >= Decimal(stop):
                return "stop_loss"
            if take is not None and price <= Decimal(take):
                return "take_profit"
            return None
        if stop is not None and price <= Decimal(stop):
            return "stop_loss"
        if take is not None and price >= Decimal(take):
            return "take_profit"
        return None
