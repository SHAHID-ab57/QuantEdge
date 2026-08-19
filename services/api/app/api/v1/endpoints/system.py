"""Platform system health, status, and metrics endpoints.

Read-only operational monitoring for the dashboard. Component probes are
live (database ping, Delta REST probe, WebSocket connection state) and
the response bodies carry per-component status so clients can render
granular states. No authentication, no trading, no AI — monitoring only.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.db.engine import probe_database
from app.db.session import get_db_or_none
from app.integrations.delta.websocket.client import DeltaConnectionSnapshot
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.runtime import Runtime, get_runtime
from app.schemas.system import (
    ComponentStatus,
    ComponentStatusValue,
    DeltaConnectionState,
    SystemHealthResponse,
    SystemMetricsResponse,
    SystemStatusResponse,
)

logger = logging.getLogger("app.api.system")

router = APIRouter(prefix="/system", tags=["system"])

RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
OptionalSessionDep = Annotated[AsyncSession | None, Depends(get_db_or_none)]

_MetricSnapshot = Mapping[str, object]


def _overall(*components: ComponentStatus) -> ComponentStatusValue:
    """Aggregate component statuses: any unavailable, else any degraded, else ok."""
    if any(component.status == "unavailable" for component in components):
        return "unavailable"
    if any(component.status == "degraded" for component in components):
        return "degraded"
    return "ok"


def _int_metric(snapshot: _MetricSnapshot | None, key: str) -> int:
    """Return an integer metric from a metrics snapshot (default 0)."""
    if snapshot is None:
        return 0
    value = snapshot.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return 0


def _float_metric(snapshot: _MetricSnapshot | None, key: str) -> float | None:
    """Return an optional float metric from a metrics snapshot."""
    if snapshot is None:
        return None
    value = snapshot.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _datetime_metric(snapshot: _MetricSnapshot | None, key: str) -> datetime | None:
    """Return an optional datetime metric from a metrics snapshot."""
    if snapshot is None:
        return None
    value = snapshot.get(key)
    return value if isinstance(value, datetime) else None


def _delta_ws_detail(snapshot: DeltaConnectionSnapshot) -> str:
    """Human-readable summary of the WebSocket connection state."""
    parts = [snapshot.state]
    parts.append(
        "authenticated" if snapshot.authenticated else "unauthenticated"
    )
    parts.append(
        f"{len(snapshot.subscriptions)} subscription(s)"
        if snapshot.subscriptions
        else "no active subscriptions"
    )
    if snapshot.last_message_at is not None:
        ago = (datetime.now(UTC) - snapshot.last_message_at).total_seconds()
        parts.append(f"last message {ago:.1f}s ago")
    return ", ".join(parts)


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="Platform component health",
    description=(
        "Return per-component status for the API, database, Delta REST and "
        "WebSocket connectivity, the event bus, and the market state manager. "
        "Always 200; component states live in the body and reflect the actual "
        "runtime state (live socket state, counters, freshness)."
    ),
)
async def system_health(runtime: RuntimeDep) -> SystemHealthResponse:
    """Probe every component and report its status."""
    api = ComponentStatus(name="api", status="ok", detail="serving requests")

    db_error = await probe_database()
    database = ComponentStatus(
        name="database",
        status="ok" if db_error is None else "unavailable",
        detail=None if db_error is None else db_error,
    )

    probe = await runtime.probe_delta_rest()
    delta_rest = ComponentStatus(
        name="delta_rest",
        status="ok" if probe.ok else "unavailable",
        latency_ms=probe.latency_ms,
        detail=(
            f"reachable in {probe.latency_ms:.0f}ms"
            if probe.ok and probe.latency_ms is not None
            else probe.error
        ),
    )

    now = datetime.now(UTC)
    snapshot = runtime.delta_connection()
    if snapshot is None:
        delta_ws = ComponentStatus(
            name="delta_ws",
            status="unavailable",
            state="stopped",
            detail="not running (set MARKET_DATA_LIVE=true)",
        )
    else:
        staleness_ms = None
        if snapshot.last_message_at is not None:
            staleness_ms = max(
                (now - snapshot.last_message_at).total_seconds() * 1000, 0.0
            )
        status: ComponentStatusValue = "ok" if snapshot.connected else "degraded"
        delta_ws = ComponentStatus(
            name="delta_ws",
            status=status,
            state=snapshot.state,
            latency_ms=staleness_ms,
            updated_at=snapshot.last_message_at,
            uptime_seconds=snapshot.uptime_seconds,
            detail=_delta_ws_detail(snapshot),
        )

    bus = runtime.bus
    event_bus = ComponentStatus(
        name="event_bus",
        status="ok",
        detail=(
            f"{bus.handler_count()} subscribers, {bus.pending_count} pending, "
            f"{bus.published_events} published, {bus.failed_handlers} failed"
        ),
    )

    state = runtime.state_manager
    state_manager = ComponentStatus(
        name="state_manager",
        status="ok",
        detail=(
            f"{len(state.symbols())} symbols tracked, "
            f"{state.metrics.state_updates} updates"
        ),
    )

    return SystemHealthResponse(
        status=_overall(api, database, delta_rest, delta_ws, event_bus, state_manager),
        api=api,
        database=database,
        delta_rest=delta_rest,
        delta_ws=delta_ws,
        event_bus=event_bus,
        state_manager=state_manager,
    )


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Platform status and freshness",
    description=(
        "Return process uptime, environment metadata, the live WebSocket "
        "connection state, the health timeline (last heartbeat, reconnect, "
        "WebSocket message, REST request), and the last ingestion time "
        "(derived from the newest stored candle close time)."
    ),
)
async def system_status(
    runtime: RuntimeDep,
    session: OptionalSessionDep,
) -> SystemStatusResponse:
    """Report platform status, uptime, and data freshness."""
    settings = get_settings()
    snapshot = runtime.delta_connection()
    connected = snapshot is not None and snapshot.connected

    db_error = await probe_database()
    status = "ok"
    if db_error is not None:
        status = "degraded"
    if runtime.market_data_live and not connected:
        status = "degraded"

    last_ingestion_at = None
    if session is not None:
        last_ingestion_at = await CandleRepository(session).latest_close_time()

    uptime_seconds = (datetime.now(UTC) - runtime.started_at).total_seconds()
    return SystemStatusResponse(
        status=status,
        started_at=runtime.started_at,
        uptime_seconds=max(uptime_seconds, 0.0),
        version=__version__,
        environment=settings.app_env,
        market_data_live=runtime.market_data_live,
        delta_ws_connected=connected,
        delta_ws=(
            DeltaConnectionState.model_validate(snapshot.__dict__)
            if snapshot is not None
            else None
        ),
        last_ws_message_at=runtime.last_ws_message_at,
        last_heartbeat_at=(
            snapshot.last_heartbeat_at if snapshot is not None else None
        ),
        last_ws_reconnect_at=(
            snapshot.connected_at if snapshot is not None else None
        ),
        last_rest_request_at=runtime.last_rest_request_at,
        last_ingestion_at=last_ingestion_at,
        symbols_tracked=len(runtime.state_manager.symbols()),
    )


@router.get(
    "/metrics",
    response_model=SystemMetricsResponse,
    summary="Platform metrics",
    description=(
        "Return counters and aggregates: stored market and candle counts, "
        "pipeline message processing, market state activity and caches, "
        "event bus load, and live WebSocket counts. DB-derived fields are "
        "null when no database is configured; pipeline fields are zero when "
        "live market data is disabled."
    ),
)
async def system_metrics(
    runtime: RuntimeDep,
    session: OptionalSessionDep,
) -> SystemMetricsResponse:
    """Report counters and aggregates for the platform stack."""
    pipeline = (
        runtime.pipeline.metrics.snapshot() if runtime.pipeline is not None else None
    )
    state = runtime.state_manager.metrics.snapshot()
    state_snapshot = runtime.state_manager.snapshot()
    bus_snapshot = runtime.bus.snapshot()

    synchronized_markets = None
    stored_candles = None
    if session is not None:
        synchronized_markets = await MarketRepository(session).count_all()
        stored_candles = await CandleRepository(session).count_all()

    latest_prices = state_snapshot["latest_prices"]
    assert isinstance(latest_prices, dict)
    return SystemMetricsResponse(
        collected_at=datetime.now(UTC),
        synchronized_markets=synchronized_markets,
        stored_candles=stored_candles,
        messages_received=_int_metric(pipeline, "messages_received"),
        messages_normalized=_int_metric(pipeline, "messages_normalized"),
        validation_failures=_int_metric(pipeline, "validation_failures"),
        unsupported_messages=_int_metric(pipeline, "unsupported_messages"),
        events_published=_int_metric(pipeline, "events_published"),
        average_pipeline_latency_ms=_float_metric(pipeline, "average_latency_ms"),
        state_updates=_int_metric(state, "state_updates"),
        invalid_events=_int_metric(state, "invalid_events"),
        state_symbols_tracked=_int_metric(state, "symbols_tracked"),
        cache_hits=_int_metric(state, "cache_hits"),
        cache_misses=_int_metric(state, "cache_misses"),
        state_latest_update_at=_datetime_metric(state_snapshot, "latest_update_at"),
        state_average_update_latency_ms=_float_metric(state, "average_update_latency_ms"),
        state_order_books_cached=_int_metric(state_snapshot, "order_books_cached"),
        state_trades_cached=_int_metric(state_snapshot, "trades_cached"),
        state_tickers_cached=_int_metric(state_snapshot, "tickers_cached"),
        state_candles_cached=_int_metric(state_snapshot, "candles_cached"),
        state_latest_prices=cast(dict[str, str], latest_prices),
        event_bus_pending=runtime.bus.pending_count,
        event_bus_subscribers=runtime.bus.handler_count(),
        event_bus_published=_int_metric(bus_snapshot, "published_events"),
        event_bus_failed_handlers=_int_metric(bus_snapshot, "failed_handlers"),
        event_bus_average_handler_latency_ms=_float_metric(
            bus_snapshot, "average_handler_latency_ms"
        ),
    )