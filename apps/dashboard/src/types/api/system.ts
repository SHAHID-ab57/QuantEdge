import { z } from 'zod';

export const ComponentStatusSchema = z.object({
  name: z.string(),
  status: z.enum(['ok', 'degraded', 'unavailable']),
  state: z.string().nullable().optional(),
  latency_ms: z.number().nonnegative().nullable().optional(),
  updated_at: z.string().datetime().nullable().optional(),
  uptime_seconds: z.number().nonnegative().nullable().optional(),
  detail: z.string().nullable().optional(),
});

export type ComponentStatus = z.infer<typeof ComponentStatusSchema>;

export const SystemHealthSchema = z.object({
  status: z.enum(['ok', 'degraded', 'unavailable']),
  api: ComponentStatusSchema,
  database: ComponentStatusSchema,
  delta_rest: ComponentStatusSchema,
  delta_ws: ComponentStatusSchema,
  event_bus: ComponentStatusSchema,
  state_manager: ComponentStatusSchema,
});

export type SystemHealth = z.infer<typeof SystemHealthSchema>;

export const DeltaConnectionStateSchema = z.object({
  state: z.enum(['stopped', 'connecting', 'connected', 'disconnected']),
  connected: z.boolean(),
  authenticated: z.boolean(),
  public: z.boolean(),
  subscriptions: z.array(z.string()),
  requested_subscriptions: z.array(z.string()),
  last_message_at: z.string().datetime().nullable(),
  last_heartbeat_at: z.string().datetime().nullable(),
  connected_at: z.string().datetime().nullable(),
  messages_received: z.number().int().nonnegative(),
  connection_attempts: z.number().int().nonnegative(),
  reconnects: z.number().int().nonnegative(),
  uptime_seconds: z.number().nonnegative().nullable(),
});

export type DeltaConnectionState = z.infer<typeof DeltaConnectionStateSchema>;

export const SystemStatusSchema = z.object({
  status: z.enum(['ok', 'degraded', 'unavailable']),
  started_at: z.string().datetime(),
  uptime_seconds: z.number().nonnegative(),
  version: z.string(),
  environment: z.string(),
  market_data_live: z.boolean(),
  delta_ws_connected: z.boolean(),
  delta_ws: DeltaConnectionStateSchema.nullable(),
  last_ws_message_at: z.string().datetime().nullable(),
  last_heartbeat_at: z.string().datetime().nullable(),
  last_ws_reconnect_at: z.string().datetime().nullable(),
  last_rest_request_at: z.string().datetime().nullable(),
  last_ingestion_at: z.string().datetime().nullable(),
  symbols_tracked: z.number().int().nonnegative(),
});

export type SystemStatus = z.infer<typeof SystemStatusSchema>;

export const SystemMetricsSchema = z.object({
  collected_at: z.string().datetime(),
  synchronized_markets: z.number().int().nonnegative().nullable(),
  stored_candles: z.number().int().nonnegative().nullable(),
  messages_received: z.number().int().nonnegative(),
  messages_normalized: z.number().int().nonnegative(),
  validation_failures: z.number().int().nonnegative(),
  unsupported_messages: z.number().int().nonnegative(),
  events_published: z.number().int().nonnegative(),
  average_pipeline_latency_ms: z.number().nonnegative().nullable(),
  state_updates: z.number().int().nonnegative(),
  invalid_events: z.number().int().nonnegative(),
  state_symbols_tracked: z.number().int().nonnegative(),
  cache_hits: z.number().int().nonnegative(),
  cache_misses: z.number().int().nonnegative(),
  state_latest_update_at: z.string().datetime().nullable(),
  state_average_update_latency_ms: z.number().nonnegative().nullable(),
  state_order_books_cached: z.number().int().nonnegative(),
  state_trades_cached: z.number().int().nonnegative(),
  state_tickers_cached: z.number().int().nonnegative(),
  state_candles_cached: z.number().int().nonnegative(),
  state_latest_prices: z.record(z.string(), z.string()),
  event_bus_pending: z.number().int().nonnegative(),
  event_bus_subscribers: z.number().int().nonnegative(),
  event_bus_published: z.number().int().nonnegative(),
  event_bus_failed_handlers: z.number().int().nonnegative(),
  event_bus_average_handler_latency_ms: z.number().nonnegative().nullable(),
});

export type SystemMetrics = z.infer<typeof SystemMetricsSchema>;

export type SystemStatusValue = 'ok' | 'degraded' | 'unavailable';
