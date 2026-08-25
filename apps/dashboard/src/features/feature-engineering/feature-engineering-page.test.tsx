import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import * as featuresApi from '@/lib/api/features';
import * as marketApi from '@/lib/api/market';
import type { Market } from '@/types/api/market';
import { FeatureEngineeringPage } from './feature-engineering-page';
import { useRecentFeaturesStore } from './store/use-recent-features-store';

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchCandlePage: vi.fn(),
}));

vi.mock('@/lib/api/features', () => ({
  fetchFeatures: vi.fn(),
  buildFeatureDataset: vi.fn(),
  exportFeatureDataset: vi.fn(),
}));

const markets: Market[] = [
  {
    id: '11111111-1111-4111-8111-111111111112',
    symbol: 'ETHUSD',
    exchange: 'Delta Exchange',
    exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
    base_asset: 'ETH',
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 3136,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.05',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: '2024-02-05T12:04:17Z',
  },
];

const catalogue = {
  features: [
    {
      name: 'ohlcv',
      label: 'OHLCV',
      description: 'Raw candle fields.',
      category: 'raw',
      parameters: [],
      outputs: ['open', 'high', 'low', 'close', 'volume'],
      version: '1.0.0',
      author: 'Eth AI Platform',
      complexity: 'O(n)',
      warmup_description: 'None.',
    },
    {
      name: 'sma',
      label: 'Simple Moving Average',
      description: 'Rolling mean.',
      category: 'trend',
      parameters: [
        {
          name: 'period',
          type: 'int' as const,
          label: 'Period',
          description: 'Window size.',
          default: 20,
          required: false,
          minimum: 1,
          maximum: 1000,
          choices: [],
        },
      ],
      outputs: ['sma_{period}'],
      version: '1.0.0',
      author: 'Eth AI Platform',
      complexity: 'O(n)',
      warmup_description: 'Equal to the period.',
    },
  ],
  total: 2,
  categories: ['raw', 'trend'],
};

const dataset = {
  dataset_id: '11111111-1111-4111-8111-111111111111',
  symbol: 'ETHUSD',
  timeframe: '1h',
  columns: [{ name: 'close', label: 'Close', description: 'Closing price.', dtype: 'float' }],
  timestamps: ['2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z'],
  rows: [[3055.25], [3180.5]],
  features: [
    {
      feature: 'ohlcv',
      label: 'OHLCV',
      version: '1.0.0',
      parameters: {},
      columns: ['close'],
      warmup: 0,
      execution_time_ms: 0.1,
    },
  ],
  meta: {
    row_count: 2,
    total_rows: 2,
    candles_analyzed: 2,
    rows_dropped: 0,
    warmup_candles: 0,
    truncated: false,
    database_time_ms: 1.4,
    pipeline_version: '1.0.0',
    generated_at: '2026-01-01T02:00:00Z',
  },
  quality: {
    total_rows: 2,
    rows_returned: 2,
    rows_removed: 0,
    null_counts: {},
    duplicate_timestamps: 0,
    missing_candles: 0,
    feature_failures: [],
    generation_time_ms: 0.4,
  },
};

const mockedMarkets = vi.mocked(marketApi);
const mockedFeatures = vi.mocked(featuresApi);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FeatureEngineeringPage />
    </QueryClientProvider>,
  );
}

/** Pick ETHUSD and the 1h timeframe in the configuration form. */
async function selectMarketAndTimeframe() {
  const marketInput = await screen.findByRole('combobox', { name: 'Select a market' });
  fireEvent.mouseDown(marketInput);
  fireEvent.change(marketInput, { target: { value: 'ETH' } });
  fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));

  const timeframe = await waitFor(() => {
    const element = screen.getByLabelText('Timeframe');
    const root = element.closest('.MuiInputBase-root') as HTMLElement;
    const control = root.querySelector('input') ?? root;
    expect(control).not.toBeDisabled();
    return element;
  });
  fireEvent.mouseDown(timeframe);
  fireEvent.click(await screen.findByRole('option', { name: '1h' }));
}

async function buildDataset() {
  await selectMarketAndTimeframe();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
  fireEvent.click(screen.getByRole('button', { name: 'Build Dataset' }));
}

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: vi.fn(() => 'blob:mock'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });
});

beforeEach(() => {
  mockedMarkets.fetchMarkets.mockResolvedValue({ markets, total: markets.length });
  mockedMarkets.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1h', '4h'] });
  mockedFeatures.fetchFeatures.mockResolvedValue(catalogue as never);
  mockedFeatures.buildFeatureDataset.mockResolvedValue(dataset as never);
  mockedFeatures.exportFeatureDataset.mockResolvedValue(new Blob(['col\n1']));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  act(() => useRecentFeaturesStore.getState().clear());
  sessionStorage.clear();
});

describe('FeatureEngineeringPage — loading and errors', () => {
  it('shows a skeleton until markets and the catalogue arrive', () => {
    mockedMarkets.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading feature engineering' })).toBeInTheDocument();
  });

  it('shows an error with a retry when the catalogue fails', async () => {
    mockedFeatures.fetchFeatures.mockRejectedValue(new Error('catalogue down'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load the feature workbench');
    expect(alert).toHaveTextContent('catalogue down');
  });

  it('recovers when Retry succeeds', async () => {
    mockedFeatures.fetchFeatures.mockRejectedValueOnce(new Error('catalogue down'));
    renderPage();
    await screen.findByRole('alert');

    mockedFeatures.fetchFeatures.mockResolvedValue(catalogue as never);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Select a market' })).toBeInTheDocument();
    });
  });

  it('prompts for configuration before anything has been built', async () => {
    renderPage();
    expect(await screen.findByText(/Choose a market, timeframe, and features/)).toBeInTheDocument();
  });
});

describe('FeatureEngineeringPage — configuration', () => {
  it('lists the catalogue grouped by category', async () => {
    renderPage();
    expect(await screen.findByText('OHLCV')).toBeInTheDocument();
    expect(screen.getByText('Simple Moving Average')).toBeInTheDocument();
    expect(screen.getByText('Raw Market Data')).toBeInTheDocument();
  });

  it('cannot build until a feature is selected', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    expect(screen.getByRole('button', { name: 'Build Dataset' })).toBeDisabled();
    expect(screen.getByText('Select at least one feature to build a dataset.')).toBeInTheDocument();
  });

  it('cannot build without a market and timeframe', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Include OHLCV' }));
    expect(screen.getByRole('button', { name: 'Build Dataset' })).toBeDisabled();
  });

  it('reports how many features are selected', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Include OHLCV' }));
    expect(screen.getByText('1 of 2 selected')).toBeInTheDocument();
  });

  it('clears the timeframe when the market changes, so a stale one is never sent', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    const marketInput = screen.getByRole('combobox', { name: 'Select a market' });
    fireEvent.mouseDown(marketInput);
    fireEvent.change(marketInput, { target: { value: 'ETH' } });
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Build Dataset' })).toBeDisabled();
    });
  });
});

describe('FeatureEngineeringPage — building', () => {
  it('builds a dataset and previews it', async () => {
    renderPage();
    await buildDataset();

    await waitFor(() => expect(mockedFeatures.buildFeatureDataset).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('3055.25')).toBeInTheDocument();
    expect(screen.getByText('3180.5')).toBeInTheDocument();
  });

  it('sends the selected market, timeframe, and features', async () => {
    renderPage();
    await buildDataset();

    await waitFor(() => expect(mockedFeatures.buildFeatureDataset).toHaveBeenCalled());
    const [symbol, params] = mockedFeatures.buildFeatureDataset.mock.calls[0]!;
    expect(symbol).toBe('ETHUSD');
    expect(params.timeframe).toBe('1h');
    expect(params.features).toEqual([{ feature: 'ohlcv', params: {} }]);
  });

  it('requests a capped preview rather than the whole dataset', async () => {
    // The browser renders the preview; the export is what must be complete.
    renderPage();
    await buildDataset();
    await waitFor(() => expect(mockedFeatures.buildFeatureDataset).toHaveBeenCalled());
    const [, params] = mockedFeatures.buildFeatureDataset.mock.calls[0]!;
    expect(params.preview_rows).toBeGreaterThan(0);
  });

  it('sends a feature’s default parameters without the researcher filling them in', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include Simple Moving Average' }));
    fireEvent.click(screen.getByRole('button', { name: 'Build Dataset' }));

    await waitFor(() => expect(mockedFeatures.buildFeatureDataset).toHaveBeenCalled());
    const [, params] = mockedFeatures.buildFeatureDataset.mock.calls[0]!;
    expect(params.features).toEqual([{ feature: 'sma', params: { period: '20' } }]);
  });

  it('does not build on selection changes, only on the explicit action', async () => {
    // Rebuilding on every checkbox tick would make the page unusable.
    renderPage();
    await selectMarketAndTimeframe();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include Simple Moving Average' }));
    expect(mockedFeatures.buildFeatureDataset).not.toHaveBeenCalled();
  });

  it('shows the dataset summary once built', async () => {
    renderPage();
    await buildDataset();
    expect(await screen.findByLabelText('Dataset summary')).toBeInTheDocument();
    expect(screen.getByText('OHLCV v1.0.0')).toBeInTheDocument();
  });

  it('shows the dataset information card once built', async () => {
    renderPage();
    await buildDataset();
    expect(await screen.findByLabelText('Dataset information')).toBeInTheDocument();
    expect(screen.getByText(dataset.dataset_id)).toBeInTheDocument();
  });

  it('surfaces a build failure with a retry action', async () => {
    mockedFeatures.buildFeatureDataset.mockRejectedValue(
      new Error('Feature "sma" needs at least 20 candles'),
    );
    renderPage();
    await buildDataset();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('needs at least 20 candles');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('rebuilds when Retry is pressed after a failure', async () => {
    mockedFeatures.buildFeatureDataset.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    await buildDataset();
    await screen.findByRole('alert');

    mockedFeatures.buildFeatureDataset.mockResolvedValue(dataset as never);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('3055.25')).toBeInTheDocument();
  });
});

describe('FeatureEngineeringPage — export', () => {
  it('offers no export before a dataset exists', async () => {
    renderPage();
    await screen.findByText('OHLCV');
    expect(screen.queryByRole('button', { name: 'Export dataset as CSV' })).not.toBeInTheDocument();
  });

  it('exports CSV once a dataset has been built', async () => {
    renderPage();
    await buildDataset();
    const csv = await screen.findByRole('button', { name: 'Export dataset as CSV' });
    fireEvent.click(csv);

    await waitFor(() => expect(mockedFeatures.exportFeatureDataset).toHaveBeenCalledTimes(1));
    expect(mockedFeatures.exportFeatureDataset.mock.calls[0]![2]).toBe('csv');
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('exports JSON', async () => {
    renderPage();
    await buildDataset();
    fireEvent.click(await screen.findByRole('button', { name: 'Export dataset as JSON' }));

    await waitFor(() => expect(mockedFeatures.exportFeatureDataset).toHaveBeenCalled());
    expect(mockedFeatures.exportFeatureDataset.mock.calls[0]![2]).toBe('json');
  });

  it('exports the request that produced the preview, so the file matches what was shown', async () => {
    renderPage();
    await buildDataset();
    fireEvent.click(await screen.findByRole('button', { name: 'Export dataset as CSV' }));

    await waitFor(() => expect(mockedFeatures.exportFeatureDataset).toHaveBeenCalled());
    const [symbol, params] = mockedFeatures.exportFeatureDataset.mock.calls[0]!;
    expect(symbol).toBe('ETHUSD');
    expect(params.features).toEqual([{ feature: 'ohlcv', params: {} }]);
  });

  it('surfaces an export failure instead of appearing to do nothing', async () => {
    // A silent failure is indistinguishable from a blocked download.
    mockedFeatures.exportFeatureDataset.mockRejectedValue(new Error('export failed'));
    renderPage();
    await buildDataset();
    fireEvent.click(await screen.findByRole('button', { name: 'Export dataset as CSV' }));

    expect(await screen.findByText('export failed')).toBeInTheDocument();
  });
});
