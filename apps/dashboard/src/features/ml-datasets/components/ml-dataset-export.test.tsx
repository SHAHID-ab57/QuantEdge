import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import * as mlDatasetsApi from '@/lib/api/ml-datasets';
import type { BuildMLDatasetParams } from '@/lib/api/ml-datasets';
import type { MLDatasetResponse } from '@/types/api/ml-datasets';
import { MLDatasetExport } from './ml-dataset-export';

vi.mock('@/lib/api/ml-datasets', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/ml-datasets')>();
  return { ...actual, exportMLDataset: vi.fn() };
});

const mockedApi = vi.mocked(mlDatasetsApi);

const params: BuildMLDatasetParams = {
  timeframe: '1h',
  features: [{ feature: 'ohlcv' }],
  targets: [{ target: 'next_close' }],
};

function dataset(): MLDatasetResponse {
  return {
    ml_dataset_id: '22222222-2222-4222-8222-222222222222',
    dataset_id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [
      { name: 'close', label: 'Close', description: '', dtype: 'float' },
      { name: 'next_close_1', label: 'Next Close', description: '', dtype: 'float' },
    ],
    feature_columns: ['close'],
    target_columns: ['next_close_1'],
    timestamps: ['2026-01-01T00:00:00Z'],
    rows: [[100, 101]],
    split: ['train'],
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
    split_bounds: { train_rows: 1, validation_rows: 0, test_rows: 0 },
    quality: {
      total_rows: 1,
      rows_returned: 1,
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
      rows: 1,
      columns: 2,
      duration_ms: 0.3,
    },
    meta: {
      row_count: 1,
      total_rows: 1,
      candles_analyzed: 2,
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
  };
}

function renderExport() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <MLDatasetExport symbol="ETHUSD" timeframe="1h" params={params} dataset={dataset()} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

/** Click the CSV/JSON button, then confirm the resulting Export Summary dialog. */
function exportViaDialog(format: 'CSV' | 'JSON') {
  fireEvent.click(screen.getByRole('button', { name: `Export ML dataset as ${format}` }));
  fireEvent.click(screen.getByRole('button', { name: 'Export' }));
}

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: vi.fn(() => 'blob:mock'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('MLDatasetExport — confirmation dialog', () => {
  it('shows the export summary dialog before exporting, rather than downloading immediately', () => {
    renderExport();
    fireEvent.click(screen.getByRole('button', { name: 'Export ML dataset as CSV' }));

    expect(screen.getByText('Export Summary')).toBeInTheDocument();
    expect(mockedApi.exportMLDataset).not.toHaveBeenCalled();
  });

  it('cancelling the dialog does not export anything', () => {
    renderExport();
    fireEvent.click(screen.getByRole('button', { name: 'Export ML dataset as CSV' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText('Export Summary')).not.toBeInTheDocument();
    expect(mockedApi.exportMLDataset).not.toHaveBeenCalled();
  });
});

describe('MLDatasetExport — exporting', () => {
  it('exports CSV via the backend and triggers a download after confirming', async () => {
    mockedApi.exportMLDataset.mockResolvedValue(new Blob(['col\n1']));
    renderExport();
    exportViaDialog('CSV');

    await waitFor(() => expect(mockedApi.exportMLDataset).toHaveBeenCalledTimes(1));
    expect(mockedApi.exportMLDataset.mock.calls[0]).toEqual(['ETHUSD', params, 'csv']);
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('exports JSON via the backend after confirming', async () => {
    mockedApi.exportMLDataset.mockResolvedValue(new Blob(['{}']));
    renderExport();
    exportViaDialog('JSON');

    await waitFor(() => expect(mockedApi.exportMLDataset).toHaveBeenCalled());
    expect(mockedApi.exportMLDataset.mock.calls[0]![2]).toBe('json');
  });

  it('surfaces an export failure instead of appearing to do nothing', async () => {
    mockedApi.exportMLDataset.mockRejectedValue(new Error('export failed'));
    renderExport();
    exportViaDialog('CSV');

    expect(await screen.findByText('export failed')).toBeInTheDocument();
  });

  it('disables both export buttons while a download is in flight', async () => {
    let resolve: (value: Blob) => void = () => undefined;
    mockedApi.exportMLDataset.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    renderExport();
    exportViaDialog('CSV');

    expect(screen.getByRole('button', { name: 'Export ML dataset as JSON' })).toBeDisabled();
    resolve(new Blob(['col\n1']));
    await waitFor(() => expect(mockedApi.exportMLDataset).toHaveBeenCalled());
  });
});
