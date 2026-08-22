"""Application runtime composition root.

Owns the in-process market data stack shared by the API process: the
event bus, the market state manager, the browser-facing streaming gateway
(``app.marketdata.gateway.MarketStreamGateway``, served at
``/api/v1/ws/market``), and — when live mode is enabled — the Delta
WebSocket client and the processing pipeline. The ``/api/v1/system/*``
endpoints read component status and metrics from this container, so the
dashboard observes the same stack the service actually runs.

Live mode is opt-in via ``MARKET_DATA_LIVE``; the bus, state manager, and
gateway are always present because they are pure in-memory and free to
run — the gateway simply has nothing to relay until live mode publishes
events.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

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
from app.services.candle_sync import CandleSyncScheduler
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

LIVE_CHANNELS = ("trades", "ticker", "ob_l1", "ob_updates")

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
        self.gateway = MarketStreamGateway(self.state_manager).attach(self.bus)
        self.pipeline: MarketDataPipeline | None = None
        self.delta_ws: DeltaWebSocketClient | None = None
        self.candle_sync: CandleSyncScheduler | None = None
        self.last_ws_message_at: datetime | None = None
        self.last_rest_request_at: datetime | None = None

    @property
    def market_data_live(self) -> bool:
        """True when the WebSocket client and pipeline are enabled."""
        return self._market_data_live

    async def start(self) -> None:
        """Start live components (pipeline + WebSocket) and the candle sync.

        The WebSocket pipeline runs only in live mode; the candle sync
        scheduler is independent and starts whenever the database is
        configured (it no-ops otherwise).
        """
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
        else:
            logger.info("Live market data disabled; WebSocket components report as not running")

        settings = get_settings()
        if settings.candle_sync_enabled:
            self.candle_sync = CandleSyncScheduler(
                interval_seconds=settings.candle_sync_interval_seconds,
                backfill_days=settings.candle_sync_backfill_days,
            )
            await self.candle_sync.start()

    async def shutdown(self) -> None:
        """Stop the WebSocket client, the candle sync loop, and drain handlers."""
        candle_sync = self.candle_sync
        if candle_sync is not None:
            await candle_sync.stop()
            self.candle_sync = None
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
