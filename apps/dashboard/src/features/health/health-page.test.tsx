import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as systemApi from '@/lib/api/system';
import { HealthPage } from './health-page';
import { SYSTEM_REFRESH_INTERVAL_MS } from './hooks/use-system-data';
import type { SystemHealth, SystemMetrics, SystemStatus } from '@/types/api/system';

const validHealth: SystemHealth = {
  status: 'ok',
  api: { name: 'api', status: 'ok', detail: 'serving requests' },
  database: { name: 'database', status: 'ok', detail: 'connected' },
  delta_rest: { name: 'delta_rest', status: 'ok', latency_ms: 12.5, detail: 'reachable in 12ms' },
  delta_ws: {
    name: 'delta_ws',
    status: 'ok',
    state: 'connected',
    latency_ms: 250,
    updated_at: '2026-08-19T10:00:00Z',
    uptime_seconds: 42,
    detail: 'connected, unauthenticated, 2 subscription(s), last message 0.3s ago',
  },
  event_bus: { name: 'event_bus', status: 'ok', detail: '4 subscribers, 0 pending' },
  state_manager: { name: 'state_manager', status: 'ok', detail: '2 symbols tracked' },
};

const validStatus: SystemStatus = {
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
    authenticated: false,
    public: true,
    subscriptions: ['trades', 'ticker'],
    requested_subscriptions: ['trades', 'ticker'],
    last_message_at: '2026-08-19T10:00:00Z',
    last_heartbeat_at: '2026-08-19T10:00:00Z',
    connected_at: '2026-08-19T09:59:00Z',
    messages_received: 28_531,
    connection_attempts: 1,
    reconnects: 0,
    uptime_seconds: 42,
  },
  last_ws_message_at: '2026-08-19T10:00:00Z',
  last_heartbeat_at: '2026-08-19T10:00:00Z',
  last_ws_reconnect_at: '2026-08-19T09:59:00Z',
  last_rest_request_at: '2026-08-19T10:00:00Z',
  last_ingestion_at: '2026-08-17T07:00:00Z',
  symbols_tracked: 2,
};

const validMetrics: SystemMetrics = {
  collected_at: '2026-08-19T10:00:00Z',
  synchronized_markets: 42,
  stored_candles: 12_345,
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

vi.mock('@/lib/api/system', () => ({
  fetchSystemHealth: vi.fn(),
  fetchSystemStatus: vi.fn(),
  fetchSystemMetrics: vi.fn(),
}));

const mocked = vi.mocked(systemApi);

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <HealthPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocked.fetchSystemHealth.mockResolvedValue(validHealth);
  mocked.fetchSystemStatus.mockResolvedValue(validStatus);
  mocked.fetchSystemMetrics.mockResolvedValue(validMetrics);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('HealthPage', () => {
  it('shows a loading skeleton before data arrives', () => {
    mocked.fetchSystemHealth.mockReturnValue(new Promise(() => undefined));
    mocked.fetchSystemStatus.mockReturnValue(new Promise(() => undefined));
    mocked.fetchSystemMetrics.mockReturnValue(new Promise(() => undefined));

    renderPage();

    expect(screen.getByRole('status', { name: 'Loading health data' })).toBeInTheDocument();
  });

  it('renders the overall status and all sections', async () => {
    renderPage();

    expect(await screen.findByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText(/All monitored components are operational/)).toBeInTheDocument();
    expect(screen.getByText('Platform')).toBeInTheDocument();
    expect(screen.getAllByText('Database').length).toBeGreaterThan(0);
    expect(screen.getByText('Delta REST')).toBeInTheDocument();
    expect(screen.getByText('Delta WebSocket')).toBeInTheDocument();
    expect(screen.getAllByText('Event Bus').length).toBeGreaterThan(0);
    expect(screen.getAllByText('State Manager').length).toBeGreaterThan(0);
    expect(screen.getByText('Health Timeline')).toBeInTheDocument();
    expect(screen.getByText('Message Processing')).toBeInTheDocument();
  });

  it('shows component-level detail and delta connection state', async () => {
    renderPage();

    expect(await screen.findByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Subscriptions')).toBeInTheDocument();
    expect(screen.getByText('Reconnects')).toBeInTheDocument();
    expect(screen.getByText('Public feed')).toBeInTheDocument();
    expect(screen.getByText('65000.5')).toBeInTheDocument();
    expect(screen.getByText('3200.25')).toBeInTheDocument();
    expect(screen.getByText('28,531')).toBeInTheDocument();
    expect(screen.getAllByText('800').length).toBeGreaterThan(0);
    expect(screen.getByText('12,345')).toBeInTheDocument();
  });

  it('shows Partially Operational when only the WebSocket is down', async () => {
    mocked.fetchSystemHealth.mockResolvedValue({
      ...validHealth,
      status: 'degraded',
      delta_ws: {
        name: 'delta_ws',
        status: 'degraded',
        state: 'disconnected',
        detail: 'disconnected (reconnecting)',
      },
    });
    mocked.fetchSystemStatus.mockResolvedValue({
      ...validStatus,
      status: 'degraded',
      delta_ws_connected: false,
      delta_ws: { ...validStatus.delta_ws!, connected: false, state: 'disconnected' },
    });

    renderPage();

    expect(await screen.findByText('Partially Operational')).toBeInTheDocument();
    expect(screen.queryByText('Critical')).not.toBeInTheDocument();
  });

  it('shows Critical when a core component is unavailable', async () => {
    mocked.fetchSystemHealth.mockResolvedValue({
      ...validHealth,
      status: 'unavailable',
      database: { name: 'database', status: 'unavailable', detail: 'connection refused' },
    });

    renderPage();

    expect(await screen.findByText('Critical')).toBeInTheDocument();
  });

  it('renders an error state and recovers on retry', async () => {
    mocked.fetchSystemHealth.mockRejectedValueOnce(new Error('boom'));

    renderPage();

    expect(await screen.findByText('Unable to load platform health')).toBeInTheDocument();

    mocked.fetchSystemHealth.mockResolvedValue(validHealth);
    const retry = screen.getByRole('button', { name: 'Try again' });
    retry.click();

    expect(await screen.findByText('Healthy')).toBeInTheDocument();
  });

  it('shows an empty notice when no data exists and live mode is off', async () => {
    mocked.fetchSystemMetrics.mockResolvedValue({
      ...validMetrics,
      synchronized_markets: null,
      stored_candles: null,
      messages_received: 0,
      state_latest_prices: {},
    });
    mocked.fetchSystemStatus.mockResolvedValue({
      ...validStatus,
      market_data_live: false,
      delta_ws_connected: false,
      delta_ws: null,
    });
    mocked.fetchSystemHealth.mockResolvedValue({
      ...validHealth,
      delta_ws: { name: 'delta_ws', status: 'unavailable', state: 'stopped' },
    });

    renderPage();

    expect(await screen.findByText(/No data recorded yet/i)).toBeInTheDocument();
  });

  it('auto-refreshes every 10 seconds', () => {
    expect(SYSTEM_REFRESH_INTERVAL_MS).toBe(10_000);
  });
});
