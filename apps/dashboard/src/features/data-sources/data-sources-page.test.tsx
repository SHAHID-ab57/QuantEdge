import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as connectorsApi from '@/lib/api/connectors';
import type { Connector, ConnectorHistory } from '@/types/api/connectors';
import { DataSourcesPage } from './data-sources-page';
import { PLANNED_CONNECTORS } from './lib/planned-connectors';

vi.mock('@/lib/api/connectors', () => ({
  fetchConnectors: vi.fn(),
  fetchConnectorHistory: vi.fn(),
}));

const mockedConnectorsApi = vi.mocked(connectorsApi);

const fearGreed: Connector = {
  source: 'fear_greed',
  label: 'Fear & Greed Index',
  description: 'A daily sentiment index.',
  frequency: 'daily',
  requires_auth: false,
  latest_value: 42,
  latest_timestamp: '2026-01-02T00:00:00Z',
};

const emptyHistory: ConnectorHistory = {
  source: 'fear_greed',
  items: [],
  pagination: { total: 0, returned: 0, has_more: false, limit: 90, offset: 0 },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DataSourcesPage />
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

describe('DataSourcesPage — Active Data Sources', () => {
  it('shows a loading state until the catalogue arrives', () => {
    mockedConnectorsApi.fetchConnectors.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading data sources' })).toBeInTheDocument();
  });

  it('renders one card per registered connector from real catalogue data', async () => {
    mockedConnectorsApi.fetchConnectors.mockResolvedValue({
      connectors: [fearGreed],
      total: 1,
    });
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Fear & Greed Index' })).toBeInTheDocument();
    expect(screen.getByText('A daily sentiment index.')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('shows an unavailable value for a connector registered but never ingested', async () => {
    mockedConnectorsApi.fetchConnectors.mockResolvedValue({
      connectors: [{ ...fearGreed, latest_value: null, latest_timestamp: null }],
      total: 1,
    });
    renderPage();

    await screen.findByRole('heading', { name: 'Fear & Greed Index' });
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.getByText('No data yet')).toBeInTheDocument();
  });

  it('shows an empty-state notice for zero registered connectors, not a crash', async () => {
    mockedConnectorsApi.fetchConnectors.mockResolvedValue({ connectors: [], total: 0 });
    renderPage();

    expect(await screen.findByText('No data sources registered yet')).toBeInTheDocument();
  });

  it('surfaces a catalogue load failure with a retry action', async () => {
    mockedConnectorsApi.fetchConnectors.mockRejectedValue(new Error('network down'));
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Failed to load data sources: network down',
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('retries the catalogue request when Retry is pressed', async () => {
    mockedConnectorsApi.fetchConnectors.mockRejectedValueOnce(new Error('network down'));
    renderPage();
    await screen.findByRole('alert');

    mockedConnectorsApi.fetchConnectors.mockResolvedValue({ connectors: [fearGreed], total: 1 });
    (await screen.findByRole('button', { name: 'Retry' })).click();

    expect(await screen.findByRole('heading', { name: 'Fear & Greed Index' })).toBeInTheDocument();
  });
});

describe('DataSourcesPage — Planned Data Sources', () => {
  it('renders its static list while the catalogue is still loading', () => {
    mockedConnectorsApi.fetchConnectors.mockReturnValue(new Promise(() => undefined));
    renderPage();

    for (const connector of PLANNED_CONNECTORS) {
      expect(screen.getByText(connector.name)).toBeInTheDocument();
    }
    expect(screen.getAllByText('Planned')).toHaveLength(PLANNED_CONNECTORS.length);
  });

  it('renders its static list even when the catalogue request fails', async () => {
    mockedConnectorsApi.fetchConnectors.mockRejectedValue(new Error('network down'));
    renderPage();

    await waitFor(() => screen.getByRole('alert'));
    for (const connector of PLANNED_CONNECTORS) {
      expect(screen.getByText(connector.name)).toBeInTheDocument();
    }
  });

  it('renders its static list once real connector data has loaded too', async () => {
    mockedConnectorsApi.fetchConnectors.mockResolvedValue({ connectors: [fearGreed], total: 1 });
    renderPage();

    await screen.findByRole('heading', { name: 'Fear & Greed Index' });
    for (const connector of PLANNED_CONNECTORS) {
      expect(screen.getByText(connector.name)).toBeInTheDocument();
    }
  });
});
