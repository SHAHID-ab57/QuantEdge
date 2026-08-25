import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { FeatureDataset } from '@/types/api/features';
import { DatasetInfoCard } from './dataset-info-card';

function dataset(overrides: Partial<FeatureDataset> = {}): FeatureDataset {
  return {
    dataset_id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [
      { name: 'close', label: 'Close', description: '', dtype: 'float' },
      { name: 'sma_20', label: 'SMA(20)', description: '', dtype: 'float' },
    ],
    timestamps: ['2026-01-01T00:00:00Z'],
    rows: [[100.5, 99.2]],
    features: [],
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

function renderCard(props: Partial<React.ComponentProps<typeof DatasetInfoCard>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <DatasetInfoCard dataset={dataset()} {...props} />
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe('DatasetInfoCard', () => {
  it('shows the dataset id', () => {
    renderCard();
    expect(screen.getByText('11111111-1111-4111-8111-111111111111')).toBeInTheDocument();
  });

  it('shows the pipeline version', () => {
    renderCard();
    expect(screen.getByText('1.0.0')).toBeInTheDocument();
  });

  it('shows the market and timeframe', () => {
    renderCard();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('1h')).toBeInTheDocument();
  });

  it('shows the full (pre-truncation) row count, not a preview count', () => {
    renderCard();
    expect(screen.getByText('480')).toBeInTheDocument();
  });

  it('shows the column count', () => {
    renderCard();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows generation time from the quality report', () => {
    renderCard();
    expect(screen.getByText('12.7 ms')).toBeInTheDocument();
  });

  it('explains what a Dataset ID is via a tooltip', () => {
    renderCard();
    expect(screen.getByRole('button', { name: 'About Dataset ID' })).toBeInTheDocument();
  });

  it('explains what the Pipeline Version is via a tooltip', () => {
    renderCard();
    expect(screen.getByRole('button', { name: 'About Pipeline Version' })).toBeInTheDocument();
  });
});
