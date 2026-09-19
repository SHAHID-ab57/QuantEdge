import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
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
