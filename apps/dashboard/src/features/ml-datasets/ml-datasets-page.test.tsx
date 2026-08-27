import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

// This file's tests each drive a market/timeframe Autocomplete, a target
// search Autocomplete, and a full page render before asserting — heavier
// than most test files here. The default 5s timeout is occasionally too
// tight only when the *entire* suite runs under parallel worker
// contention (never when this file runs alone), so it's raised file-wide
// rather than patched per test.
vi.setConfig({ testTimeout: 15000 });
import * as marketApi from '@/lib/api/market';
import * as featuresApi from '@/lib/api/features';
import * as mlDatasetsApi from '@/lib/api/ml-datasets';
import type { Market } from '@/types/api/market';
import type { MLDatasetBuildSummary, MLDatasetResponse } from '@/types/api/ml-datasets';
import { MLDatasetsPage } from './ml-datasets-page';
import { useRecentFeaturesStore } from '@/features/feature-engineering/store/use-recent-features-store';

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

vi.mock('@/lib/api/ml-datasets', () => ({
  fetchTargets: vi.fn(),
  fetchTarget: vi.fn(),
  buildMLDataset: vi.fn(),
  exportMLDataset: vi.fn(),
  fetchMLDatasetBuilds: vi.fn(),
  fetchMLDatasetBuild: vi.fn(),
  deleteMLDatasetBuild: vi.fn(),
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

const featureCatalogue = {
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
  ],
  total: 1,
  categories: ['raw'],
};

const targetCatalogue = {
  targets: [
    {
      name: 'next_close',
      label: 'Next Close Price',
      description: 'The close price N candles ahead.',
      category: 'price',
      parameters: [
        {
          name: 'horizon',
          type: 'int' as const,
          label: 'Horizon',
          description: 'Candles ahead.',
          default: 1,
          required: false,
          minimum: 1,
          maximum: 500,
          choices: [],
        },
      ],
      outputs: ['next_close_{horizon}'],
      version: '1.0.0',
      author: 'Eth AI Platform',
      value_type: 'float',
      default_horizon: 1,
      is_deterministic: true,
    },
  ],
  total: 1,
  categories: ['price'],
};

function mlDataset(overrides: Partial<MLDatasetResponse> = {}): MLDatasetResponse {
  return {
    ml_dataset_id: '22222222-2222-4222-8222-222222222222',
    dataset_id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [
      { name: 'close', label: 'Close', description: 'Closing price.', dtype: 'float' },
      {
        name: 'next_close_1',
        label: 'Next Close (1)',
        description: 'Future close.',
        dtype: 'float',
      },
    ],
    feature_columns: ['close'],
    target_columns: ['next_close_1'],
    timestamps: ['2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z'],
    rows: [
      [3055.25, 3180.5],
      [3180.5, 3200.0],
    ],
    split: ['train', 'validation'],
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
    targets: [
      {
        target: 'next_close',
        label: 'Next Close Price',
        version: '1.0.0',
        parameters: { horizon: 1 },
        columns: ['next_close_1'],
        horizon: 1,
        execution_time_ms: 0.2,
      },
    ],
    target_failures: [],
    split_ratios: { train: 0.7, validation: 0.15, test: 0.15 },
    split_bounds: { train_rows: 1, validation_rows: 1, test_rows: 0 },
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
    validation: {
      dataset_id: '11111111-1111-4111-8111-111111111111',
      symbol: 'ETHUSD',
      timeframe: '1h',
      engine_version: '1.0.0',
      validated_at: '2026-01-01T02:00:00Z',
      passed: true,
      rules_run: ['no_nulls'],
      summary: { total_checks: 1, errors: 0, warnings: 0, info: 0 },
      categories: {},
      issues: [],
      rows: 2,
      columns: 2,
      duration_ms: 0.3,
    },
    meta: {
      row_count: 2,
      total_rows: 2,
      candles_analyzed: 3,
      rows_dropped_warmup: 0,
      rows_dropped_horizon: 1,
      warmup_candles: 0,
      max_horizon: 1,
      truncated: false,
      database_time_ms: 1.4,
      pipeline_version: '1.0.0',
      target_pipeline_version: '1.0.0',
      builder_version: '1.0.0',
      generated_at: '2026-01-01T02:00:00Z',
      created_at: '2026-01-01T02:00:00Z',
    },
    ...overrides,
  };
}

function buildSummary(overrides: Partial<MLDatasetBuildSummary> = {}): MLDatasetBuildSummary {
  return {
    id: '33333333-3333-4333-8333-333333333333',
    ml_dataset_id: '22222222-2222-4222-8222-222222222222',
    symbol: 'ETHUSD',
    timeframe: '1h',
    row_count: 2,
    column_count: 2,
    feature_count: 1,
    target_count: 1,
    quality_passed: true,
    created_at: '2026-01-01T02:00:00Z',
    ...overrides,
  };
}

const mockedMarkets = vi.mocked(marketApi);
const mockedFeatures = vi.mocked(featuresApi);
const mockedMlDatasets = vi.mocked(mlDatasetsApi);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MLDatasetsPage />
    </QueryClientProvider>,
  );
}

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

function selectNextClosePrice() {
  const input = screen.getByRole('combobox', { name: 'Search prediction targets' });
  fireEvent.mouseDown(input);
  fireEvent.click(screen.getByRole('option', { name: /Next Close Price/ }));
}

async function buildDataset() {
  await selectMarketAndTimeframe();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
  selectNextClosePrice();
  fireEvent.click(screen.getByRole('button', { name: 'Build ML Dataset' }));
}

/** Click the CSV/JSON export button, then confirm the resulting Export Summary dialog. */
function exportViaDialog(format: 'CSV' | 'JSON') {
  fireEvent.click(screen.getByRole('button', { name: `Export ML dataset as ${format}` }));
  fireEvent.click(screen.getByRole('button', { name: 'Export' }));
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
  mockedFeatures.fetchFeatures.mockResolvedValue(featureCatalogue as never);
  mockedMlDatasets.fetchTargets.mockResolvedValue(targetCatalogue as never);
  mockedMlDatasets.buildMLDataset.mockResolvedValue(mlDataset());
  mockedMlDatasets.exportMLDataset.mockResolvedValue(new Blob(['col\n1']));
  mockedMlDatasets.fetchMLDatasetBuilds.mockResolvedValue({
    builds: [],
    total: 0,
    limit: 10,
    offset: 0,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  act(() => useRecentFeaturesStore.getState().clear());
  sessionStorage.clear();
});

describe('MLDatasetsPage — loading and errors', () => {
  it('shows a skeleton until markets and both catalogues arrive', () => {
    mockedMarkets.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading ML dataset builder' })).toBeInTheDocument();
  });

  it('shows an error with a retry when the target catalogue fails', async () => {
    mockedMlDatasets.fetchTargets.mockRejectedValue(new Error('targets down'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load the ML dataset builder');
    expect(alert).toHaveTextContent('targets down');
  });

  it('prompts for configuration before anything has been built', async () => {
    renderPage();
    expect(
      await screen.findByText(/Choose a market, timeframe, features, and prediction targets/),
    ).toBeInTheDocument();
  });
});

describe('MLDatasetsPage — configuration', () => {
  it('lists the feature and target catalogues', async () => {
    renderPage();
    expect(await screen.findByText('OHLCV')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Search prediction targets' }));
    expect(screen.getByRole('option', { name: /Next Close Price/ })).toBeInTheDocument();
  });

  it('cannot build until a feature and a target are both selected', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    expect(screen.getByRole('button', { name: 'Build ML Dataset' })).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
    expect(screen.getByRole('button', { name: 'Build ML Dataset' })).toBeDisabled();
    expect(
      screen.getByText('Select at least one prediction target to build a dataset.'),
    ).toBeInTheDocument();

    selectNextClosePrice();
    expect(screen.getByRole('button', { name: 'Build ML Dataset' })).not.toBeDisabled();
  });

  it('cannot build when the split ratios do not sum to 1.0', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
    selectNextClosePrice();
    fireEvent.change(screen.getByLabelText('Train ratio'), { target: { value: '0.5' } });

    expect(screen.getByRole('button', { name: 'Build ML Dataset' })).toBeDisabled();
  });

  it('does not build on selection changes, only on the explicit action', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
    selectNextClosePrice();
    expect(mockedMlDatasets.buildMLDataset).not.toHaveBeenCalled();
  });
});

describe('MLDatasetsPage — building and preview', () => {
  it('builds an ML dataset and previews it, including the split column', async () => {
    renderPage();
    await buildDataset();

    await waitFor(() => expect(mockedMlDatasets.buildMLDataset).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('3055.25')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Split' })).toBeInTheDocument();
    expect(screen.getByText('train')).toBeInTheDocument();
    expect(screen.getByText('validation')).toBeInTheDocument();
  });

  it('sends the selected market, timeframe, features, targets, and split ratios', async () => {
    renderPage();
    await buildDataset();

    await waitFor(() => expect(mockedMlDatasets.buildMLDataset).toHaveBeenCalled());
    const [symbol, params] = mockedMlDatasets.buildMLDataset.mock.calls[0]!;
    expect(symbol).toBe('ETHUSD');
    expect(params.timeframe).toBe('1h');
    expect(params.features).toEqual([{ feature: 'ohlcv', params: {} }]);
    expect(params.targets).toEqual([{ target: 'next_close', params: { horizon: '1' } }]);
    expect(params.split_train).toBe(0.7);
    expect(params.split_validation).toBe(0.15);
    expect(params.split_test).toBe(0.15);
  });

  it('marks the target column in the preview table', async () => {
    renderPage();
    await buildDataset();
    await waitFor(() => expect(mockedMlDatasets.buildMLDataset).toHaveBeenCalled());
    expect(await screen.findByText('target')).toBeInTheDocument();
  });

  it('shows the ML dataset information card once built', async () => {
    renderPage();
    await buildDataset();
    const card = await screen.findByLabelText('ML dataset information');
    expect(within(card).getByText(mlDataset().ml_dataset_id)).toBeInTheDocument();
  });

  it('shows the dataset summary once built', async () => {
    renderPage();
    await buildDataset();
    expect(await screen.findByLabelText('ML dataset summary')).toBeInTheDocument();
  });

  it('shows the validation verdict once built', async () => {
    renderPage();
    await buildDataset();
    const summary = await screen.findByLabelText('Validation summary');
    expect(within(summary).getByText('Passed')).toBeInTheDocument();
  });

  it('surfaces a build failure with a retry action', async () => {
    mockedMlDatasets.buildMLDataset.mockRejectedValue(new Error('horizon too large'));
    renderPage();
    await buildDataset();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('horizon too large');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('rebuilds when Retry is pressed after a failure', async () => {
    mockedMlDatasets.buildMLDataset.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    await buildDataset();
    await screen.findByRole('alert');

    mockedMlDatasets.buildMLDataset.mockResolvedValue(mlDataset());
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('3055.25')).toBeInTheDocument();
  });

  it('surfaces target generation failures without blocking the rest of the dataset', async () => {
    mockedMlDatasets.buildMLDataset.mockResolvedValue(
      mlDataset({
        target_failures: [
          {
            target: 'next_return',
            params: {},
            error_code: 'insufficient_data',
            error_detail: 'needs more candles',
          },
        ],
      }),
    );
    renderPage();
    await buildDataset();
    expect(await screen.findByText(/1 target failed to generate/)).toBeInTheDocument();
    expect(screen.getByText(/needs more candles/)).toBeInTheDocument();
  });
});

describe('MLDatasetsPage — export', () => {
  it('offers no export before a dataset exists', async () => {
    renderPage();
    await screen.findByText('OHLCV');
    expect(
      screen.queryByRole('button', { name: 'Export ML dataset as CSV' }),
    ).not.toBeInTheDocument();
  });

  it('shows an export summary dialog before exporting CSV', async () => {
    renderPage();
    await buildDataset();
    await screen.findByRole('button', { name: 'Export ML dataset as CSV' });
    fireEvent.click(screen.getByRole('button', { name: 'Export ML dataset as CSV' }));

    expect(screen.getByText('Export Summary')).toBeInTheDocument();
    expect(mockedMlDatasets.exportMLDataset).not.toHaveBeenCalled();
  });

  it('exports CSV once confirmed', async () => {
    renderPage();
    await buildDataset();
    await screen.findByRole('button', { name: 'Export ML dataset as CSV' });
    exportViaDialog('CSV');

    await waitFor(() => expect(mockedMlDatasets.exportMLDataset).toHaveBeenCalledTimes(1));
    expect(mockedMlDatasets.exportMLDataset.mock.calls[0]![2]).toBe('csv');
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('exports JSON once confirmed', async () => {
    renderPage();
    await buildDataset();
    await screen.findByRole('button', { name: 'Export ML dataset as JSON' });
    exportViaDialog('JSON');

    await waitFor(() => expect(mockedMlDatasets.exportMLDataset).toHaveBeenCalled());
    expect(mockedMlDatasets.exportMLDataset.mock.calls[0]![2]).toBe('json');
  });

  it('exports the request that produced the preview, so the file matches what was shown', async () => {
    renderPage();
    await buildDataset();
    await screen.findByRole('button', { name: 'Export ML dataset as CSV' });
    exportViaDialog('CSV');

    await waitFor(() => expect(mockedMlDatasets.exportMLDataset).toHaveBeenCalled());
    const [symbol, params] = mockedMlDatasets.exportMLDataset.mock.calls[0]!;
    expect(symbol).toBe('ETHUSD');
    expect(params.targets).toEqual([{ target: 'next_close', params: { horizon: '1' } }]);
  });

  it('surfaces an export failure instead of appearing to do nothing', async () => {
    mockedMlDatasets.exportMLDataset.mockRejectedValue(new Error('export failed'));
    renderPage();
    await buildDataset();
    await screen.findByRole('button', { name: 'Export ML dataset as CSV' });
    exportViaDialog('CSV');

    expect(await screen.findByText('export failed')).toBeInTheDocument();
  });
});

describe('MLDatasetsPage — metadata and reproducibility', () => {
  it('shows the dataset metadata panel once built', async () => {
    renderPage();
    await buildDataset();
    expect(await screen.findByLabelText('ML dataset metadata')).toBeInTheDocument();
    expect(screen.getByText('ChronologicalSplitter')).toBeInTheDocument();
  });

  it('offers Copy/Import Configuration controls before anything has been built', async () => {
    renderPage();
    await screen.findByText('OHLCV');
    expect(screen.getByRole('button', { name: 'Copy Configuration' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import Configuration' })).toBeInTheDocument();
  });

  it('imports a pasted configuration and restores the market/timeframe/split', async () => {
    renderPage();
    await screen.findByText('OHLCV');
    fireEvent.click(screen.getByRole('button', { name: 'Import Configuration' }));
    fireEvent.change(screen.getByLabelText('Paste dataset configuration JSON'), {
      target: {
        value: JSON.stringify({
          market: 'ETHUSD',
          timeframe: '1h',
          range: 'all',
          start: '',
          end: '',
          limit: 500,
          features: [{ feature: 'ohlcv', params: {} }],
          targets: [{ target: 'next_close', params: { horizon: '1' } }],
          split: { train: 0.7, validation: 0.15, test: 0.15 },
        }),
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() =>
      expect(screen.queryByText('Import Dataset Configuration')).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getAllByText('1 of 1 selected')).toHaveLength(2));
    expect(screen.getByRole('button', { name: 'Build ML Dataset' })).not.toBeDisabled();
  });
});

describe('MLDatasetsPage — Dataset History', () => {
  it('lists past builds', async () => {
    mockedMlDatasets.fetchMLDatasetBuilds.mockResolvedValue({
      builds: [buildSummary()],
      total: 1,
      limit: 10,
      offset: 0,
    });
    renderPage();

    expect(await screen.findByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('Passed')).toBeInTheDocument();
  });

  it('shows the empty state when nothing has been built yet', async () => {
    renderPage();
    expect(
      await screen.findByText(
        'No datasets built yet — use the builder above, and it will appear here.',
      ),
    ).toBeInTheDocument();
  });

  it('reopens a past build in a detail dialog', async () => {
    mockedMlDatasets.fetchMLDatasetBuilds.mockResolvedValue({
      builds: [buildSummary()],
      total: 1,
      limit: 10,
      offset: 0,
    });
    mockedMlDatasets.fetchMLDatasetBuild.mockResolvedValue({
      id: '33333333-3333-4333-8333-333333333333',
      created_at: '2026-01-01T02:00:00Z',
      dataset: mlDataset(),
    });
    renderPage();

    fireEvent.click(await screen.findByText('ETHUSD'));

    expect(await screen.findByText('ML Dataset Information')).toBeInTheDocument();
    expect(screen.getByText('Dataset Preview')).toBeInTheDocument();
  });

  it('deletes a past build after confirming', async () => {
    mockedMlDatasets.fetchMLDatasetBuilds.mockResolvedValue({
      builds: [buildSummary()],
      total: 1,
      limit: 10,
      offset: 0,
    });
    mockedMlDatasets.deleteMLDatasetBuild.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('ETHUSD');

    fireEvent.click(screen.getByLabelText('Delete ML dataset build ETHUSD 1h'));
    expect(await screen.findByText('Delete Dataset Build')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() =>
      expect(mockedMlDatasets.deleteMLDatasetBuild).toHaveBeenCalledWith(
        '33333333-3333-4333-8333-333333333333',
      ),
    );
  });

  it('backing out of the delete confirmation does not delete the build', async () => {
    mockedMlDatasets.fetchMLDatasetBuilds.mockResolvedValue({
      builds: [buildSummary()],
      total: 1,
      limit: 10,
      offset: 0,
    });
    renderPage();
    await screen.findByText('ETHUSD');

    fireEvent.click(screen.getByLabelText('Delete ML dataset build ETHUSD 1h'));
    await screen.findByText('Delete Dataset Build');
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));

    await waitFor(() => expect(screen.queryByText('Delete Dataset Build')).not.toBeInTheDocument());
    expect(mockedMlDatasets.deleteMLDatasetBuild).not.toHaveBeenCalled();
  });

  it('a newly built dataset appears in history once building succeeds', async () => {
    renderPage();
    await buildDataset();

    await waitFor(() => expect(mockedMlDatasets.fetchMLDatasetBuilds).toHaveBeenCalledTimes(2));
  });
});
