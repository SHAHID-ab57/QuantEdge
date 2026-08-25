import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { FeatureDataset } from '@/types/api/features';
import { DatasetSummary } from './dataset-summary';

function dataset(overrides: Partial<FeatureDataset> = {}): FeatureDataset {
  return {
    dataset_id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [{ name: 'sma_20', label: 'SMA(20)', description: '', dtype: 'float' }],
    timestamps: ['2026-01-01T00:00:00Z'],
    rows: [[100.5]],
    features: [
      {
        feature: 'sma',
        label: 'SMA',
        version: '1.0.0',
        parameters: {},
        columns: ['sma_20'],
        warmup: 20,
        execution_time_ms: 0.1,
      },
    ],
    meta: {
      row_count: 1,
      total_rows: 480,
      candles_analyzed: 500,
      rows_dropped: 20,
      warmup_candles: 20,
      truncated: false,
      database_time_ms: 4.2,
      pipeline_version: '1.0.0',
      generated_at: '2026-01-01T02:00:00Z',
    },
    quality: {
      total_rows: 500,
      rows_returned: 480,
      rows_removed: 20,
      null_counts: {},
      duplicate_timestamps: 0,
      missing_candles: 0,
      feature_failures: [],
      generation_time_ms: 12.7,
    },
    ...overrides,
  };
}

function renderSummary(props: Partial<React.ComponentProps<typeof DatasetSummary>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <DatasetSummary dataset={dataset()} {...props} />
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe('DatasetSummary — core metrics', () => {
  it('shows candles read and rows dropped', () => {
    renderSummary();
    expect(screen.getByText('500')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });

  it('names the feature responsible for the largest warmup', () => {
    renderSummary();
    expect(screen.getByText(/SMA needs 20 candles before its first value/)).toBeInTheDocument();
  });

  it('shows no warmup notice when nothing was dropped', () => {
    renderSummary({ dataset: dataset({ meta: { ...dataset().meta, rows_dropped: 0 } }) });
    expect(screen.queryByText(/warmup/)).not.toBeInTheDocument();
  });
});

describe('DatasetSummary — quality report', () => {
  it('shows duplicate timestamps and missing candles', () => {
    renderSummary({
      dataset: dataset({
        quality: { ...dataset().quality, duplicate_timestamps: 2, missing_candles: 3 },
      }),
    });
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('flags columns that still contain nulls', () => {
    renderSummary({
      dataset: dataset({ quality: { ...dataset().quality, null_counts: { candle_body: 4 } } }),
    });
    expect(screen.getByText(/Null values remain in column candle_body/)).toBeInTheDocument();
  });

  it('does not mention nulls when there are none', () => {
    renderSummary();
    expect(screen.queryByText(/Null values remain/)).not.toBeInTheDocument();
  });

  it('surfaces feature failures without hiding the rest of the report', () => {
    renderSummary({
      dataset: dataset({
        quality: {
          ...dataset().quality,
          feature_failures: [
            {
              feature: 'ema',
              params: { period: '999' },
              error_code: 'insufficient_data',
              error_detail: "Feature 'ema' needs at least 999 candles",
            },
          ],
        },
      }),
    });
    expect(screen.getByText('1 feature failed to generate')).toBeInTheDocument();
    expect(screen.getByText(/needs at least 999 candles/)).toBeInTheDocument();
  });

  it('reports no failures when everything succeeded', () => {
    renderSummary();
    expect(screen.queryByText(/failed to generate/)).not.toBeInTheDocument();
  });

  it('lists every feature with its version', () => {
    renderSummary();
    expect(screen.getByText('SMA v1.0.0')).toBeInTheDocument();
  });
});
