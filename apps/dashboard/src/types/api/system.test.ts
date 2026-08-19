import { describe, expect, it } from 'vitest';
import {
  ComponentStatusSchema,
  DeltaConnectionStateSchema,
  SystemHealthSchema,
  SystemMetricsSchema,
  SystemStatusSchema,
} from './system';

const baseHealth = {
  status: 'ok',
  api: { name: 'api', status: 'ok', detail: 'serving requests' },
  database: { name: 'database', status: 'ok', detail: null },
  delta_rest: { name: 'delta_rest', status: 'ok', detail: 'reachable in 12ms' },
  delta_ws: {
    name: 'delta_ws',
    status: 'ok',
    state: 'connected',
    latency_ms: 250,
    updated_at: '2026-08-19T10:00:00Z',
    uptime_seconds: 42,
    detail: 'connected, authenticated, 4 subscription(s)',
  },
  event_bus: { name: 'event_bus', status: 'ok', detail: '4 subscribers' },
  state_manager: { name: 'state_manager', status: 'ok', detail: '2 symbols tracked' },
};

const baseStatus = {
  status: 'ok',
  started_at: '2026-08-19T10:00:00Z',
  uptime_seconds: 300,
  version: '0.1.0',
  environment: 'development',
  market_data_live: true,
  delta_ws_connected: true,
  delta_ws: {
    state: 'connected',
    connected: true,
    authenticated: true,
    public: false,
    subscriptions: ['trades', 'ticker'],
    requested_subscriptions: ['trades', 'ticker'],
    last_message_at: '2026-08-19T10:00:00Z',
    last_heartbeat_at: '2026-08-19T10:00:00Z',
    connected_at: '2026-08-19T09:59:00Z',
    messages_received: 28_531,
    connection_attempts: 3,
    reconnects: 2,
    uptime_seconds: 42,
  },
  last_ws_message_at: '2026-08-19T10:00:00Z',
  last_heartbeat_at: '2026-08-19T10:00:00Z',
  last_ws_reconnect_at: '2026-08-19T09:59:00Z',
  last_rest_request_at: '2026-08-19T10:00:00Z',
  last_ingestion_at: '2026-08-17T07:00:00Z',
  symbols_tracked: 2,
};

const baseMetrics = {
  collected_at: '2026-08-19T10:00:00Z',
  synchronized_markets: 225,
  stored_candles: 79,
  messages_received: 1000,
  messages_normalized: 900,
  validation_failures: 3,
  unsupported_messages: 2,
  events_published: 800,
  average_pipeline_latency_ms: 0.5,
  state_updates: 500,
  invalid_events: 0,
  state_symbols_tracked: 2,
  cache_hits: 10,
  cache_misses: 1,
  state_latest_update_at: '2026-08-19T10:00:00Z',
  state_average_update_latency_ms: 0.05,
  state_order_books_cached: 2,
  state_trades_cached: 2,
  state_tickers_cached: 2,
  state_candles_cached: 5,
  state_latest_prices: { BTCUSD: '65000.5', ETHUSD: '3200.25' },
  event_bus_pending: 0,
  event_bus_subscribers: 4,
  event_bus_published: 800,
  event_bus_failed_handlers: 0,
  event_bus_average_handler_latency_ms: 0.12,
};

describe('SystemHealthSchema', () => {
  it('accepts a fully-populated payload', () => {
    expect(() => SystemHealthSchema.parse(baseHealth)).not.toThrow();
  });

  it('accepts minimal component statuses (legacy shape)', () => {
    expect(ComponentStatusSchema.parse({ name: 'api', status: 'ok' })).toBeDefined();
    expect(ComponentStatusSchema.parse({ name: 'api', status: 'degraded' })).toBeDefined();
    expect(ComponentStatusSchema.parse({ name: 'api', status: 'unavailable' })).toBeDefined();
  });

  it('rejects an unknown component status value', () => {
    expect(() => ComponentStatusSchema.parse({ name: 'api', status: 'down' })).toThrow();
  });

  it('rejects a payload missing a component', () => {
    const missing: Record<string, unknown> = { ...baseHealth };
    delete missing.api;
    expect(() => SystemHealthSchema.parse(missing)).toThrow();
  });
});

describe('SystemStatusSchema', () => {
  it('accepts a populated payload with connection state', () => {
    expect(() => SystemStatusSchema.parse(baseStatus)).not.toThrow();
  });

  it('accepts a null delta_ws when live mode is off', () => {
    const offline = {
      ...baseStatus,
      market_data_live: false,
      delta_ws: null,
      delta_ws_connected: false,
    };
    expect(() => SystemStatusSchema.parse(offline)).not.toThrow();
  });

  it('validates the delta connection state enum', () => {
    expect(() =>
      DeltaConnectionStateSchema.parse({ ...baseStatus.delta_ws, state: 'connected' }),
    ).not.toThrow();
    expect(() =>
      DeltaConnectionStateSchema.parse({ ...baseStatus.delta_ws, state: 'weird' }),
    ).toThrow();
  });
});

describe('SystemMetricsSchema', () => {
  it('accepts a populated payload', () => {
    expect(() => SystemMetricsSchema.parse(baseMetrics)).not.toThrow();
  });

  it('accepts an offline payload with nulls and zeroes', () => {
    const offline = {
      ...baseMetrics,
      synchronized_markets: null,
      stored_candles: null,
      state_latest_update_at: null,
      state_latest_prices: {},
    };
    expect(() => SystemMetricsSchema.parse(offline)).not.toThrow();
  });

  it('rejects a non-string price value', () => {
    const bad = { ...baseMetrics, state_latest_prices: { BTCUSD: 65000.5 } };
    expect(() => SystemMetricsSchema.parse(bad)).toThrow();
  });
});
