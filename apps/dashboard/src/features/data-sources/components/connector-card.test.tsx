import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { createTheme } from '@mui/material/styles';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as connectorsApi from '@/lib/api/connectors';
import type { Connector, ConnectorHistory } from '@/types/api/connectors';
import { ConnectorCard } from './connector-card';

vi.mock('@/lib/api/connectors', () => ({
  fetchConnectorHistory: vi.fn(),
}));

const mockedConnectorsApi = vi.mocked(connectorsApi);

const emptyHistory: ConnectorHistory = {
  source: 'fear_greed',
  items: [],
  pagination: { total: 0, returned: 0, has_more: false, limit: 90, offset: 0 },
};

const baseConnector: Connector = {
  source: 'fear_greed',
  label: 'Fear & Greed Index',
  description: 'A daily sentiment index.',
  frequency: 'daily',
  requires_auth: false,
  latest_value: 42,
  latest_timestamp: '2026-01-02T00:00:00Z',
  health_status: 'healthy',
  expected_interval_seconds: 86_400,
  total_points: 120,
  last_attempt_at: '2030-01-02T00:05:00Z',
  last_attempt_success: true,
  next_sync_at: '2030-01-03T00:05:00Z',
};

function renderCard(connector: Connector) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ConnectorCard connector={connector} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedConnectorsApi.fetchConnectorHistory.mockResolvedValue(emptyHistory);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ConnectorCard — health status', () => {
  it('shows a Healthy pill for a healthy connector', () => {
    renderCard({ ...baseConnector, health_status: 'healthy' });
    expect(screen.getByText('Healthy')).toBeInTheDocument();
  });

  it('shows a Stale pill for a stale connector', () => {
    renderCard({ ...baseConnector, health_status: 'stale' });
    expect(screen.getByText('Stale')).toBeInTheDocument();
  });

  it('shows a Failing pill for a connector whose recent syncs all errored, even with fresh data', () => {
    renderCard({ ...baseConnector, health_status: 'failing' });
    expect(screen.getByText('Failing')).toBeInTheDocument();
    // The last good value is still shown; failing is about the sync, not the data on screen.
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('shows a Never ingested pill for a connector with no data yet', () => {
    renderCard({
      ...baseConnector,
      latest_value: null,
      latest_timestamp: null,
      health_status: 'never_ingested',
    });
    expect(screen.getByText('Never ingested')).toBeInTheDocument();
  });
});

describe('ConnectorCard — card treatment by health', () => {
  /** The card itself (the section), not the pill inside it. */
  function cardStyle(health_status: Connector['health_status']) {
    const { container } = renderCard({ ...baseConnector, health_status });
    const card = container.querySelector('section');
    if (!card) throw new Error('card section not rendered');
    const style = getComputedStyle(card);
    return {
      status: card.getAttribute('data-health-status'),
      border: style.borderTopColor,
      ring: style.boxShadow,
      background: style.backgroundColor,
    };
  }

  afterEach(cleanup);

  it('exposes the health status on the card for inspection', () => {
    expect(cardStyle('failing').status).toBe('failing');
  });

  // jsdom does not resolve the CSS variable MUI uses for an untinted Paper's
  // (absent) shadow, so "no ring" is asserted as "no explicit ring drawn",
  // not as the literal `none` a real browser reports.
  const RING = '0 0 0 1px';
  const errorColor = createTheme().palette.error.main;

  it('tints a failing card: a red border, an outer ring in the error color, and a red wash', () => {
    const healthy = cardStyle('healthy');
    cleanup();
    const failing = cardStyle('failing');

    expect(failing.border).not.toBe(healthy.border);
    expect(failing.background).not.toBe(healthy.background);
    // The ring is drawn outside the box (box-shadow), never a thicker border,
    // so a failing card cannot change size and shift the grid.
    expect(failing.ring).toContain(RING);
    expect(failing.ring.toLowerCase()).toContain(errorColor.toLowerCase());
    expect(healthy.ring).not.toContain(RING);
  });

  it('tints a stale card, more quietly than a failing one, with no ring', () => {
    const healthy = cardStyle('healthy');
    cleanup();
    const stale = cardStyle('stale');
    cleanup();
    const failing = cardStyle('failing');

    expect(stale.border).not.toBe(healthy.border);
    expect(stale.border).not.toBe(failing.border);
    expect(stale.background).not.toBe(healthy.background);
    expect(stale.background).not.toBe(failing.background);
    expect(stale.ring).not.toContain(RING);
  });

  it('leaves healthy and never-ingested cards untinted, identical to each other', () => {
    const healthy = cardStyle('healthy');
    cleanup();
    const neverIngested = cardStyle('never_ingested');

    expect(neverIngested.border).toBe(healthy.border);
    expect(neverIngested.background).toBe(healthy.background);
    expect(neverIngested.ring).toBe(healthy.ring);
    expect(healthy.ring).not.toContain(RING);
  });
});

describe('ConnectorCard — value precision', () => {
  it('does not round a small nonzero value down to a misleading zero', () => {
    // The real ETHUSD Funding Rate bug: 0.0001 (0.01% per 8h) used to
    // render as a bare "0", indistinguishable from a genuinely zero rate.
    renderCard({ ...baseConnector, latest_value: 0.0001 });
    expect(screen.getByText('0.0001')).toBeInTheDocument();
  });
});

describe('ConnectorCard — sync status', () => {
  it('shows when the source was last fetched, distinct from the value date', () => {
    renderCard({
      ...baseConnector,
      last_attempt_at: '2030-01-02T00:03:00Z',
      last_attempt_success: true,
    });
    expect(screen.getByText(/^Fetched/)).toBeInTheDocument();
  });

  it('shows a failed fetch attempt distinctly from a successful one', () => {
    renderCard({ ...baseConnector, last_attempt_success: false });
    expect(screen.getByText(/^Fetch failed/)).toBeInTheDocument();
  });

  it('shows no sync attempted yet when the scheduler has never touched this source', () => {
    renderCard({ ...baseConnector, last_attempt_at: null, last_attempt_success: null });
    expect(screen.getByText('No sync attempted yet')).toBeInTheDocument();
  });

  it('flags an overdue next sync — the real Open Interest staleness cause', () => {
    // `next_sync_at` in the past means the scheduler missed its own tick,
    // which is what actually explained a `stale` pill with no other context.
    renderCard({ ...baseConnector, next_sync_at: '2000-01-01T00:00:00Z' });
    expect(screen.getByText(/^Next sync overdue by/)).toBeInTheDocument();
  });

  it('counts down to a future projected sync when on schedule', () => {
    const soon = new Date(Date.now() + 5 * 60_000).toISOString();
    renderCard({ ...baseConnector, next_sync_at: soon });
    expect(screen.getByText(/^Next sync in/)).toBeInTheDocument();
  });

  it('shows the total stored points and the expected cadence', () => {
    renderCard({ ...baseConnector, total_points: 2_880, expected_interval_seconds: 28_800 });
    expect(screen.getByText('2,880 points stored · every 8h')).toBeInTheDocument();
  });
});
