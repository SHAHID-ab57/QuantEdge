import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { Indicator, IndicatorCalculation } from '@/types/api/indicators';
import { getIndicatorKnowledge } from '../lib/indicator-knowledge';
import { IndicatorResults } from './indicator-results';

afterEach(() => {
  cleanup();
});

function smaIndicator(): Indicator {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'Unweighted mean.',
    category: 'trend',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period parameter.',
    parameters: [],
    outputs: [{ name: 'sma', label: 'SMA', description: '' }],
  };
}

function calculation(overrides: Partial<IndicatorCalculation> = {}): IndicatorCalculation {
  return {
    symbol: 'ETHUSD',
    timeframe: '1h',
    indicator: smaIndicator(),
    parameters: { period: 2, source: 'close' },
    timestamps: ['2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z', '2026-01-01T02:00:00Z'],
    series: [{ name: 'sma', label: 'SMA(2)', values: [null, 17.5, 28] }],
    meta: {
      candles_analyzed: 3,
      warmup_candles: 2,
      execution_time_ms: 0.12,
      database_time_ms: 4.5,
      cache_status: 'miss',
      generated_at: '2026-01-01T03:00:00Z',
    },
    ...overrides,
  };
}

function renderResults(overrides: Partial<IndicatorCalculation> = {}, maxRows?: number) {
  const result = calculation(overrides);
  return render(
    <ThemeProvider theme={theme}>
      <IndicatorResults
        result={result}
        knowledge={getIndicatorKnowledge(result.indicator)}
        maxRows={maxRows}
      />
    </ThemeProvider>,
  );
}

describe('IndicatorResults', () => {
  it('renders a summary card naming the latest value', () => {
    renderResults();
    // "SMA(2)" appears both in the summary card and the chart legend.
    expect(screen.getAllByText('SMA(2)').length).toBeGreaterThanOrEqual(2);
    const summary = screen.getByRole('status', { name: 'Indicator summary' });
    expect(within(summary).getByText('28')).toBeInTheDocument();
  });

  it('renders a chart for the computed series', () => {
    renderResults();
    expect(screen.getByRole('img', { name: 'SMA(2) chart' })).toBeInTheDocument();
  });

  it('reports candles analyzed and warmup separately, each with an info tooltip', () => {
    renderResults();
    const meta = screen.getByRole('status', { name: 'Calculation metadata' });
    expect(within(meta).getByText('Candles Analyzed')).toBeInTheDocument();
    expect(within(meta).getByText('Warmup Candles')).toBeInTheDocument();
    expect(
      within(meta).getByRole('button', { name: 'About Candles Analyzed' }),
    ).toBeInTheDocument();
    expect(within(meta).getByRole('button', { name: 'About Warmup Candles' })).toBeInTheDocument();
  });

  it('separates calculation time from the database read', () => {
    renderResults();
    expect(screen.getByText('0.12 ms')).toBeInTheDocument();
    expect(screen.getByText('4.5 ms loading candles')).toBeInTheDocument();
  });

  it('reports the cache status', () => {
    renderResults({ meta: { ...calculation().meta, cache_status: 'hit' } });
    expect(screen.getByText('hit')).toBeInTheDocument();
  });

  it('renders one table row per candle, newest first', () => {
    renderResults();
    const table = screen.getByRole('table', { name: 'Indicator values' });
    const rows = within(table).getAllByRole('row').slice(1); // drop the header
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('28');
  });

  it('renders warmup nulls as an em dash in the table', () => {
    renderResults();
    const table = screen.getByRole('table', { name: 'Indicator values' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows[2]).toHaveTextContent('—'); // the oldest row is warmup
  });

  it('renders a column per output series', () => {
    renderResults({
      series: [
        { name: 'upper', label: 'Upper', values: [1, 2, 3] },
        { name: 'lower', label: 'Lower', values: [0, 1, 2] },
      ],
    });
    expect(screen.getByRole('columnheader', { name: 'Upper' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Lower' })).toBeInTheDocument();
  });

  it('caps the table and says so when the series is longer than maxRows', () => {
    renderResults(
      {
        timestamps: Array.from({ length: 10 }, (_, i) =>
          new Date(Date.UTC(2026, 0, 1, i)).toISOString(),
        ),
        series: [{ name: 'sma', label: 'SMA(2)', values: Array.from({ length: 10 }, (_, i) => i) }],
      },
      4,
    );
    expect(screen.getByText(/showing 4 of 10/)).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Indicator values' });
    expect(within(table).getAllByRole('row').slice(1)).toHaveLength(4);
  });

  it('does not claim truncation when everything fits', () => {
    renderResults();
    expect(screen.queryByText(/showing/)).not.toBeInTheDocument();
  });

  it('exposes a results-table info tooltip', () => {
    renderResults();
    expect(screen.getByRole('button', { name: 'About Results Table' })).toBeInTheDocument();
  });
});
