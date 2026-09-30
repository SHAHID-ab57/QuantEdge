"""Application runtime composition root.

Owns the in-process market data stack shared by the API process: the
event bus, the market state manager, the order book aggregator
(``app.marketdata.orderbook.OrderBookAggregator`` — reconstructs a
coherent per-symbol L2 book from the state manager's own last-writer-wins
event stream, see its module docstring for why that reconstruction can't
live in the state manager itself), the browser-facing streaming gateway
(``app.marketdata.gateway.MarketStreamGateway``, served at
``/api/v1/ws/market``), the paper trading stop-loss/take-profit monitor
(``app.paper_trading.monitor.StopLossTakeProfitMonitor`` — subscribes to
the same live-price events, gated on its own at the database layer rather
than here, see that module's own docstring), and — when live mode is
enabled — the Delta WebSocket client and the processing pipeline. The
``/api/v1/system/*`` endpoints read component status and metrics from
this container, so the dashboard observes the same stack the service
actually runs.

Live mode is opt-in via ``MARKET_DATA_LIVE``; the bus, state manager,
order book aggregator, gateway, and stop-loss/take-profit monitor are
always present because they are pure in-memory to construct and free to
run — the gateway simply has nothing to relay, and the monitor nothing
to trigger, until live mode (or a test) actually publishes events.

The paper trading automated strategy
(``app.services.paper_trading_strategy.PaperTradingStrategyScheduler``)
and the funding scheduler (``app.services.paper_funding.PaperFundingScheduler``)
are gated on their own settings, database-optional, and stay here rather
than in the standalone scheduler process (``app.scheduler_main``) because
both read live price state from ``self.state_manager`` — the same reason
``StopLossTakeProfitMonitor`` and ``OrderFlowCapture`` stay here too. See
``docs/infrastructure/EVENT_LOOP_SEPARATION_DESIGN.md`` for the full
reasoning. Unlike the monitor, the strategy scheduler is *not* always-on:
the real per-account opt-in (``PaperAccount.strategy_enabled``, off by
default) lives in the database, not here — this flag only controls
whether the loop that checks for enabled accounts runs at all.

Candle sync, prediction grading, external-data sync, news sync, and
retraining have no such dependency — they only ever touch the database
and outbound REST APIs — so they run in the separate ``app.scheduler_main``
process instead, off this process's event loop entirely (moved there to
resolve a confirmed, measured DB-connection-timeout contention pattern;
see ``docs/infrastructure/WORKER_HEADROOM_CHECK.md`` and
``EVENT_LOOP_SEPARATION_DESIGN.md``). This module no longer builds or
starts any of them.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.config import get_settings
from app.events.bus import EventBus
from app.integrations.delta.client import DeltaClient
from app.integrations.delta.config import DeltaConfig
from app.integrations.delta.websocket.client import (
    DeltaConnectionSnapshot,
    DeltaWebSocketClient,
    get_delta_ws_client,
)
from app.marketdata import DeltaNormalizer, MarketDataPipeline
from app.marketdata.gateway import MarketStreamGateway
from app.marketdata.orderbook import OrderBookAggregator
from app.paper_trading.monitor import StopLossTakeProfitMonitor
from app.services.order_flow_capture import OrderFlowCapture
from app.services.paper_funding import PaperFundingScheduler
from app.services.paper_trading_strategy import PaperTradingStrategyScheduler
from app.state import MarketStateManager
from app.ws.models import WSEvent

__all__ = [
    "DeltaRestProbeResult",
    "Runtime",
    "build_runtime",
    "get_runtime",
    "shutdown_runtime",
    "start_runtime",
]

logger = logging.getLogger("app.runtime")

LIVE_CHANNELS = ("trades", "ticker", "ob_l1", "ob_updates", "funding_rate")

REST_PROBE_PATH = "/v2/products"
REST_PROBE_TIMEOUT = 5.0
REST_PROBE_MAX_RETRIES = 0


@dataclass(frozen=True)
class DeltaRestProbeResult:
    """Outcome of one Delta REST availability probe."""

    ok: bool
    latency_ms: float | None
    error: str | None


class Runtime:
    """Composition root for the in-process market data stack.

    The bus and state manager are always constructed; the pipeline and
    WebSocket client exist only in live mode (see :meth:`start`).
    """

    def __init__(
        self,
        *,
        market_data_live: bool,
        symbols: tuple[str, ...],
        started_at: datetime,
    ) -> None:
        self._market_data_live = market_data_live
        self._symbols = symbols
        self.started_at = started_at
        self.bus = EventBus()
        self.state_manager = MarketStateManager().attach(self.bus)
        self.order_book = OrderBookAggregator().attach(self.bus)
        self.gateway = MarketStreamGateway(self.state_manager, self.order_book).attach(self.bus)
        settings = get_settings()
        self.stop_loss_take_profit_monitor = StopLossTakeProfitMonitor(
            state_manager=self.state_manager,
            slippage_bps=settings.paper_trading_slippage_bps,
            fee_bps=settings.paper_trading_fee_bps,
            triggered_slippage_bps=settings.paper_trading_triggered_slippage_bps,
            staleness_threshold=timedelta(
                seconds=settings.paper_trading_stale_price_threshold_seconds
            ),
            default_max_position_size_pct=settings.paper_trading_default_max_position_size_pct,
            default_max_exposure_pct=settings.paper_trading_default_max_exposure_pct,
            default_max_drawdown_pct=settings.paper_trading_default_max_drawdown_pct,
            max_order_attempts=settings.paper_trading_max_order_attempts,
            default_strategy_confidence_threshold_pct=(
                settings.paper_trading_strategy_default_confidence_threshold_pct
            ),
            default_strategy_default_stop_loss_pct=(
                settings.paper_trading_strategy_default_stop_loss_pct
            ),
            default_max_leverage=settings.paper_trading_default_max_leverage,
            maintenance_margin_rate=settings.paper_trading_maintenance_margin_pct / Decimal(100),
            max_leverage_notional=settings.paper_trading_max_leverage_notional,
        ).attach(self.bus)
        # Order-flow capture only makes sense with the live pipeline publishing
        # bus events; attaching (and thus buffering trades) is pointless
        # otherwise, so it is constructed conditionally, not started-and-idle.
        self.order_flow_capture: OrderFlowCapture | None = None
        if settings.orderflow_capture_enabled and market_data_live:
            self.order_flow_capture = OrderFlowCapture(
                aggregator=self.order_book,
                symbols=self._symbols,
                snapshot_interval_seconds=settings.orderflow_snapshot_interval_seconds,
                snapshot_depth=settings.orderflow_snapshot_depth,
                trade_flush_seconds=settings.orderflow_trade_flush_seconds,
                trade_buffer_max=settings.orderflow_trade_buffer_max,
                retention_days=settings.orderflow_retention_days,
                prune_interval_seconds=settings.orderflow_prune_interval_seconds,
            ).attach(self.bus)
        self.pipeline: MarketDataPipeline | None = None
        self.delta_ws: DeltaWebSocketClient | None = None
        self.paper_trading_strategy: PaperTradingStrategyScheduler | None = None
        self.paper_funding: PaperFundingScheduler | None = None
        self.last_ws_message_at: datetime | None = None
        self.last_rest_request_at: datetime | None = None

    @property
    def market_data_live(self) -> bool:
        """True when the WebSocket client and pipeline are enabled."""
        return self._market_data_live

    async def start(self) -> None:
        """Start live components (pipeline + WebSocket) and the live-state-
        coupled schedulers (paper trading strategy, funding).

        The WebSocket pipeline runs only in live mode. Candle sync,
        prediction grading, external-data sync, news sync, Reddit sync, and
        retraining no longer start here — they run in the separate
        `app.scheduler_main` process (see this module's own docstring).
        """
        logger.info(
            "Candle sync, prediction grading, external-data sync, news sync, Reddit "
            "sync, and retraining do NOT run in this process — start "
            "`app.scheduler_main` separately (`make run-scheduler`) or every source "
            "those six own will silently stop advancing with no error here"
        )
        if self._market_data_live:
            self.pipeline = MarketDataPipeline(
                normalizer=DeltaNormalizer(),
                bus=self.bus,
            )
            self.delta_ws = get_delta_ws_client()
            symbols = list(self._symbols) or None
            for channel in LIVE_CHANNELS:
                self.delta_ws.add_listener(channel, self.pipeline.handle)
            self.delta_ws.add_listener("*", self._on_ws_event)
            for channel in LIVE_CHANNELS:
                await self.delta_ws.subscribe(channel, symbols)
            self.delta_ws.start()
            logger.info(
                "Live market data started (symbols=%s, channels=%s)",
                ",".join(self._symbols) or "*",
                ",".join(LIVE_CHANNELS),
            )
            if self.order_flow_capture is not None:
                await self.order_flow_capture.start()
        else:
            logger.info("Live market data disabled; WebSocket components report as not running")

        settings = get_settings()
        if settings.paper_trading_strategy_scheduler_enabled:
            self.paper_trading_strategy = PaperTradingStrategyScheduler(
                state_manager=self.state_manager,
                interval_seconds=settings.paper_trading_strategy_interval_seconds,
            )
            await self.paper_trading_strategy.start()
        if settings.paper_trading_funding_enabled:
            self.paper_funding = PaperFundingScheduler(
                state_manager=self.state_manager,
                interval_seconds=settings.paper_trading_funding_interval_seconds,
                lookback_hours=settings.paper_trading_funding_lookback_hours,
            )
            await self.paper_funding.start()

    async def shutdown(self) -> None:
        """Stop the WebSocket client, the live-state-coupled schedulers, and drain handlers."""
        paper_trading_strategy = self.paper_trading_strategy
        if paper_trading_strategy is not None:
            await paper_trading_strategy.stop()
            self.paper_trading_strategy = None
        paper_funding = self.paper_funding
        if paper_funding is not None:
            await paper_funding.stop()
            self.paper_funding = None
        order_flow_capture = self.order_flow_capture
        if order_flow_capture is not None:
            await order_flow_capture.stop()
        ws = self.delta_ws
        if ws is not None:
            await ws.close()
            self.delta_ws = None
            self.pipeline = None
            logger.info("Live market data stopped")
        await self.bus.drain()

    async def probe_delta_rest(self) -> DeltaRestProbeResult:
        """Probe Delta REST availability with a time-boxed, retry-free GET.

        Never raises: any failure is reported as an unavailable probe.
        """
        self.last_rest_request_at = datetime.now(UTC)
        settings = get_settings()
        config = DeltaConfig(
            base_url=settings.delta_base_url,
            api_key=settings.delta_api_key,
            api_secret=settings.delta_api_secret,
            request_timeout=min(settings.delta_request_timeout, REST_PROBE_TIMEOUT),
        )
        client = DeltaClient(config, max_retries=REST_PROBE_MAX_RETRIES)
        started = time.perf_counter()
        try:
            await client.get(REST_PROBE_PATH, params={"page_size": 1, "states": "live"})
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.warning("Delta REST probe failed: %s", exc)
            return DeltaRestProbeResult(ok=False, latency_ms=latency_ms, error=str(exc))
        finally:
            await client.aclose()
        latency_ms = (time.perf_counter() - started) * 1000
        return DeltaRestProbeResult(ok=True, latency_ms=latency_ms, error=None)

    async def _on_ws_event(self, _event: WSEvent) -> None:
        """Stamp the most recent dispatched WebSocket message time."""
        self.last_ws_message_at = datetime.now(UTC)

    def delta_connection(self) -> DeltaConnectionSnapshot | None:
        """Live WebSocket connection snapshot, or ``None`` when not running."""
        if self.delta_ws is None:
            return None
        return self.delta_ws.connection_snapshot()


_runtime: Runtime | None = None


def build_runtime() -> Runtime:
    """Return the process-wide runtime, building it lazily on first use.

    When the lifespan has not run (tests, tooling), an offline runtime is
    built so health endpoints still respond without network or database.
    """
    global _runtime

    if _runtime is None:
        settings = get_settings()
        symbols = tuple(
            part.strip() for part in settings.delta_market_symbols.split(",") if part.strip()
        )
        _runtime = Runtime(
            market_data_live=settings.market_data_live,
            symbols=symbols,
            started_at=datetime.now(UTC),
        )
    return _runtime


async def start_runtime() -> None:
    """Start the process-wide runtime (called from the lifespan startup)."""
    await build_runtime().start()


async def shutdown_runtime() -> None:
    """Stop the process-wide runtime (called from the lifespan shutdown)."""
    global _runtime

    if _runtime is not None:
        await _runtime.shutdown()
        _runtime = None


def get_runtime() -> Runtime:
    """FastAPI dependency: return the process-wide runtime."""
    return build_runtime()
