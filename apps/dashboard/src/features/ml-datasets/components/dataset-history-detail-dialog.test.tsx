import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import * as mlDatasetsApi from '@/lib/api/ml-datasets';
import type { MLDatasetBuildDetailResponse } from '@/types/api/ml-datasets';
import { DatasetHistoryDetailDialog } from './dataset-history-detail-dialog';

vi.mock('@/lib/api/ml-datasets', () => ({
  fetchTargets: vi.fn(),
  fetchMLDatasetBuild: vi.fn(),
}));

const mockedApi = vi.mocked(mlDatasetsApi);

function detail(): MLDatasetBuildDetailResponse {
  return {
    id: 'build-1',
    created_at: '2026-01-01T02:00:00Z',
    dataset: {
      ml_dataset_id: 'ml-1',
      dataset_id: 'ds-1',
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
        [100, 101],
        [101, 102],
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
        dataset_id: 'ds-1',
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
    },
  };
}

function renderDialog(buildId: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>
        <DatasetHistoryDetailDialog buildId={buildId} onClose={vi.fn()} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedApi.fetchTargets.mockResolvedValue({ targets: [], total: 0, categories: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DatasetHistoryDetailDialog', () => {
  it('renders nothing when no build is selected', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ThemeProvider theme={theme}>
          <DatasetHistoryDetailDialog buildId={null} onClose={vi.fn()} />
        </ThemeProvider>
      </QueryClientProvider>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a loading indicator while fetching', () => {
    mockedApi.fetchMLDatasetBuild.mockReturnValue(new Promise(() => undefined));
    renderDialog('build-1');
    expect(screen.getByLabelText('Loading dataset build')).toBeInTheDocument();
  });

  it('renders the full stored dataset once loaded', async () => {
    mockedApi.fetchMLDatasetBuild.mockResolvedValue(detail());
    renderDialog('build-1');

    expect(await screen.findByRole('heading', { name: 'ETHUSD · 1h' })).toBeInTheDocument();
    expect(screen.getByText('ML Dataset Information')).toBeInTheDocument();
    expect(screen.getByText('Dataset Summary')).toBeInTheDocument();
    expect(screen.getByText('Dataset Preview')).toBeInTheDocument();
  });

  it('surfaces a load error', async () => {
    mockedApi.fetchMLDatasetBuild.mockRejectedValue(new Error('not found'));
    renderDialog('build-1');

    expect(await screen.findByRole('alert')).toHaveTextContent('not found');
  });
});
