import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { SystemHealth, SystemStatus } from '@/types/api/system';
import { ConnectionStatus } from './connection-status';

afterEach(() => {
  cleanup();
});

const NOW = Date.parse('2026-01-01T12:00:00Z');

function component(status: 'ok' | 'degraded' | 'unavailable', latency: number | null = null) {
  return { name: 'x', status, latency_ms: latency };
}

function health(overrides: Partial<SystemHealth> = {}): SystemHealth {
  return {
    status: 'ok',
    api: component('ok', 4.2),
    database: component('ok'),
    delta_rest: component('ok'),
    delta_ws: component('ok'),
    event_bus: component('ok'),
    state_manager: component('ok'),
    ...overrides,
  } as SystemHealth;
}

function status(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    status: 'ok',
    started_at: '2026-01-01T00:00:00Z',
    uptime_seconds: 100,
    version: '0.1.0',
    environment: 'test',
    market_data_live: true,
    delta_ws_connected: true,
    delta_ws: null,
    last_ws_message_at: null,
    last_heartbeat_at: null,
    last_ws_reconnect_at: null,
    last_rest_request_at: null,
    last_ingestion_at: '2026-01-01T11:58:00Z',
    symbols_tracked: 2,
    ...overrides,
  } as SystemStatus;
}

function renderPanel(props: Partial<React.ComponentProps<typeof ConnectionStatus>> = {}) {
  return render(
    <ConnectionStatus
      connectionState="open"
      lastMessageAt={NOW - 1_000}
      reconnectAttempt={0}
      latencyMs={12}
      health={health()}
      healthError={false}
      status={status()}
      now={NOW}
      {...props}
    />,
  );
}

describe('ConnectionStatus', () => {
  it('reports every dependency the live view needs', () => {
    renderPanel();
    for (const label of [
      'Backend API',
      'WebSocket',
      'Historical Sync',
      'Market State',
      'Last Message',
      'Reconnect Attempts',
      'Latency',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('shows the backend API status with its measured latency', () => {
    renderPanel();
    expect(screen.getByText('ok · 4ms')).toBeInTheDocument();
  });

  it('reports the backend as unreachable when the health query fails', () => {
    renderPanel({ health: undefined, healthError: true });
    expect(screen.getByText('Unreachable')).toBeInTheDocument();
  });

  it('shows the stream heartbeat round-trip as the latency figure', () => {
    renderPanel({ latencyMs: 37 });
    expect(screen.getByText('37ms')).toBeInTheDocument();
  });

  it('says latency is unavailable before the first heartbeat returns', () => {
    renderPanel({ latencyMs: null });
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
  });

  it('counts reconnect attempts while reconnecting', () => {
    renderPanel({ connectionState: 'reconnecting', reconnectAttempt: 3 });
    expect(screen.getAllByText('Reconnecting…').length).toBeGreaterThan(0);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('flags historical sync that has fallen behind', () => {
    renderPanel({ status: status({ last_ingestion_at: '2026-01-01T10:00:00Z' }) });
    expect(screen.getByText('2h ago')).toBeInTheDocument();
  });

  it('reports how many symbols the backend holds live state for', () => {
    renderPanel();
    expect(screen.getByText('ok · 2 symbols')).toBeInTheDocument();
  });

  it('shows Disconnected when the stream is closed', () => {
    renderPanel({ connectionState: 'closed', lastMessageAt: null });
    expect(screen.getAllByText('Disconnected').length).toBeGreaterThan(0);
    expect(screen.getByText('None yet')).toBeInTheDocument();
  });
});
