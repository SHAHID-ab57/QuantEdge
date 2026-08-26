import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import * as datasetValidationApi from '@/lib/api/dataset-validation';
import * as featuresApi from '@/lib/api/features';
import * as marketApi from '@/lib/api/market';
import type { Market } from '@/types/api/market';
import { DatasetValidationPage } from './dataset-validation-page';

// This file's tests each drive a market/timeframe Autocomplete plus a full
// page render before asserting — heavier than most test files here. The
// default 5s timeout is occasionally too tight only when the *entire*
// suite runs under parallel worker contention (never when this file runs
// alone), so it's raised file-wide rather than patched per test — the
// same fix already applied to `ml-datasets-page.test.tsx` for the
// identical reason.
vi.setConfig({ testTimeout: 15000 });

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchCandlePage: vi.fn(),
}));

vi.mock('@/lib/api/features', () => ({
  fetchFeatures: vi.fn(),
}));

vi.mock('@/lib/api/dataset-validation', () => ({
  fetchValidationRules: vi.fn(),
  validateDataset: vi.fn(),
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

const ruleCatalogue = {
  rules: [
    {
      name: 'required_columns',
      category: 'structural',
      description: 'Every required column exists.',
      default_severity: 'error' as const,
      version: '1.0.0',
    },
  ],
  total: 1,
  categories: ['structural'],
};

const passingReport = {
  dataset_id: '11111111-1111-4111-8111-111111111111',
  symbol: 'ETHUSD',
  timeframe: '1h',
  engine_version: '1.0.0',
  validated_at: '2026-01-01T00:00:00Z',
  passed: true,
  rules_run: ['required_columns'],
  summary: { total_checks: 0, errors: 0, warnings: 0, info: 0 },
  categories: {
    structural: { errors: 0, warnings: 0, info: 0 },
    data_quality: { errors: 0, warnings: 0, info: 0 },
    time_series: { errors: 0, warnings: 0, info: 0 },
    feature: { errors: 0, warnings: 0, info: 0 },
  },
  issues: [],
  rows: 2,
  columns: 5,
  duration_ms: 1.1,
};

const failingReport = {
  ...passingReport,
  passed: false,
  summary: { total_checks: 1, errors: 1, warnings: 0, info: 0 },
  issues: [
    {
      rule: 'duplicate_timestamps',
      category: 'data_quality',
      severity: 'error' as const,
      code: 'duplicate_timestamps',
      message: '1 timestamp(s) appear more than once',
      column: null,
      row_index: null,
      count: 1,
      details: {},
    },
  ],
};

const mockedMarkets = vi.mocked(marketApi);
const mockedFeatures = vi.mocked(featuresApi);
const mockedValidation = vi.mocked(datasetValidationApi);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DatasetValidationPage />
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

async function runValidation() {
  await selectMarketAndTimeframe();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
  fireEvent.click(screen.getByRole('button', { name: 'Run Validation' }));
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
  mockedValidation.fetchValidationRules.mockResolvedValue(ruleCatalogue as never);
  mockedValidation.validateDataset.mockResolvedValue(passingReport as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

describe('DatasetValidationPage — loading and errors', () => {
  it('shows a skeleton until markets and the catalogue arrive', () => {
    mockedMarkets.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading dataset validation' })).toBeInTheDocument();
  });

  it('shows an error with a retry when the catalogue fails', async () => {
    mockedFeatures.fetchFeatures.mockRejectedValue(new Error('catalogue down'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load the validation workbench');
    expect(alert).toHaveTextContent('catalogue down');
  });
});

describe('DatasetValidationPage — empty state', () => {
  it('explains what validation does, how to start, and an example workflow', async () => {
    renderPage();
    expect(await screen.findByText('What validation does')).toBeInTheDocument();
    expect(screen.getByText('How to start')).toBeInTheDocument();
    expect(screen.getByText('Example workflow')).toBeInTheDocument();
  });
});

describe('DatasetValidationPage — configuration', () => {
  it('reuses the feature catalogue selector', async () => {
    renderPage();
    expect(await screen.findByText('OHLCV')).toBeInTheDocument();
  });

  it('cannot run validation until a feature is selected', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    expect(screen.getByRole('button', { name: 'Run Validation' })).toBeDisabled();
    expect(
      screen.getByText('Select at least one feature to validate a dataset.'),
    ).toBeInTheDocument();
  });

  it('shows the available rule catalogue grouped by category', async () => {
    renderPage();
    expect(await screen.findByText('Available Checks')).toBeInTheDocument();
    expect(await screen.findByText('required_columns')).toBeInTheDocument();
  });

  it('explains every configurable field via a tooltip', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: 'About Market' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About Required columns' })).toBeInTheDocument();
  });
});

describe('DatasetValidationPage — required columns selector', () => {
  it('sends columns chosen through the searchable selector', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));

    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Required columns' }));
    fireEvent.click(screen.getByRole('option', { name: /close/ }));

    fireEvent.click(screen.getByRole('button', { name: 'Run Validation' }));
    await waitFor(() => expect(mockedValidation.validateDataset).toHaveBeenCalledTimes(1));
    const [, params] = mockedValidation.validateDataset.mock.calls[0]!;
    expect(params.required_columns).toEqual(['close']);
  });

  it('applying a preset seeds both the feature selection and required columns', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    fireEvent.click(screen.getByRole('button', { name: 'Apply OHLCV Only preset' }));

    expect(screen.getByText('1 of 2 selected')).toBeInTheDocument();
    expect(screen.getByText('(5 selected)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Run Validation' }));
    await waitFor(() => expect(mockedValidation.validateDataset).toHaveBeenCalledTimes(1));
    const [, params] = mockedValidation.validateDataset.mock.calls[0]!;
    expect(params.features).toEqual([{ feature: 'ohlcv', params: {} }]);
    expect(params.required_columns?.sort()).toEqual(['close', 'high', 'low', 'open', 'volume']);
  });
});

describe('DatasetValidationPage — running validation', () => {
  it('sends the same market/timeframe/feature selection the request needs', async () => {
    renderPage();
    await runValidation();
    await waitFor(() => expect(mockedValidation.validateDataset).toHaveBeenCalledTimes(1));
    const [symbol, params] = mockedValidation.validateDataset.mock.calls[0]!;
    expect(symbol).toBe('ETHUSD');
    expect(params.timeframe).toBe('1h');
    expect(params.features).toEqual([{ feature: 'ohlcv', params: {} }]);
  });

  it('shows the summary cards, statistics, and download action once validated', async () => {
    renderPage();
    await runValidation();
    expect(await screen.findByText('Passed')).toBeInTheDocument();
    expect(screen.getByText('Validation Summary')).toBeInTheDocument();
    expect(screen.getByText('Validation Report')).toBeInTheDocument();
    expect(screen.getByText('Statistics')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Download validation report as JSON' }),
    ).toBeInTheDocument();
  });

  it('shows failing issues in the unified report panel', async () => {
    mockedValidation.validateDataset.mockResolvedValue(failingReport as never);
    renderPage();
    await runValidation();
    expect(await screen.findByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('1 timestamp(s) appear more than once')).toBeInTheDocument();
  });

  it('shows an inline error with retry when validation fails', async () => {
    mockedValidation.validateDataset.mockRejectedValueOnce(new Error('validation down'));
    renderPage();
    await runValidation();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('validation down');

    mockedValidation.validateDataset.mockResolvedValue(passingReport as never);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Passed')).toBeInTheDocument();
  });
});
