"""Response schemas for the platform system endpoints.

Health reports per-component statuses; status reports process and data
freshness; metrics reports counters and aggregates. DB-derived fields are
``None`` when no database is configured, never fabricated.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ComponentStatusValue = Literal["ok", "degraded", "unavailable"]


class ComponentStatus(BaseModel):
    """Status of a single platform component.

    ``state``, ``latency_ms``, ``updated_at``, and ``uptime_seconds`` are
    optional richer signals the dashboard renders when present.
    """

    name: str
    status: ComponentStatusValue
    state: str | None = None
    latency_ms: float | None = None
    updated_at: datetime | None = None
    uptime_seconds: float | None = None
    detail: str | None = None


class DeltaConnectionState(BaseModel):
    """Live WebSocket connection state reported from the runtime."""

    state: Literal["stopped", "connecting", "connected", "disconnected"]
    connected: bool
    authenticated: bool
    public: bool
    subscriptions: list[str] = []
    requested_subscriptions: list[str] = []
    last_message_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    connected_at: datetime | None = None
    messages_received: int = 0
    connection_attempts: int = 0
    reconnects: int = 0
    uptime_seconds: float | None = None


class SystemHealthResponse(BaseModel):
    """Per-component health of the platform."""

    status: ComponentStatusValue
    api: ComponentStatus
    database: ComponentStatus
    delta_rest: ComponentStatus
    delta_ws: ComponentStatus
    event_bus: ComponentStatus
    state_manager: ComponentStatus


class SystemStatusResponse(BaseModel):
    """Process and data freshness overview."""

    status: ComponentStatusValue
    started_at: datetime
    uptime_seconds: float
    version: str
    environment: str
    market_data_live: bool
    delta_ws_connected: bool
    delta_ws: DeltaConnectionState | None = None
    last_ws_message_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_ws_reconnect_at: datetime | None = None
    last_rest_request_at: datetime | None = None
    last_ingestion_at: datetime | None = None
    symbols_tracked: int


class SystemMetricsResponse(BaseModel):
    """Counters and aggregates for the platform stack."""

    collected_at: datetime
    synchronized_markets: int | None = None
    stored_candles: int | None = None
    messages_received: int = 0
    messages_normalized: int = 0
    validation_failures: int = 0
    unsupported_messages: int = 0
    events_published: int = 0
    average_pipeline_latency_ms: float | None = None
    state_updates: int = 0
    invalid_events: int = 0
    state_symbols_tracked: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    state_latest_update_at: datetime | None = None
    state_average_update_latency_ms: float | None = None
    state_order_books_cached: int = 0
    state_trades_cached: int = 0
    state_tickers_cached: int = 0
    state_candles_cached: int = 0
    state_latest_prices: dict[str, str] = {}
    event_bus_pending: int = 0
    event_bus_subscribers: int = 0
    event_bus_published: int = 0
    event_bus_failed_handlers: int = 0
    event_bus_average_handler_latency_ms: float | None = None
