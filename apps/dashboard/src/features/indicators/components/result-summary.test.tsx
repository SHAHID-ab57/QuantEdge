import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { Indicator, IndicatorSeries } from '@/types/api/indicators';
import { getIndicatorKnowledge } from '../lib/indicator-knowledge';
import { ResultSummary } from './result-summary';

afterEach(() => {
  cleanup();
});

function catalogueEntry(name: string): Indicator {
  return {
    name,
    label: name.toUpperCase(),
    description: 'Stub.',
    category: 'trend',
    parameters: [],
    outputs: [],
  };
}

function renderSummary(series: IndicatorSeries[], indicatorName = 'sma') {
  return render(
    <ThemeProvider theme={theme}>
      <ResultSummary
        series={series}
        knowledge={getIndicatorKnowledge(catalogueEntry(indicatorName))}
      />
    </ThemeProvider>,
  );
}

describe('ResultSummary', () => {
  it('shows the latest and previous values', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [null, 100, 110] }]);
    expect(screen.getByText('110')).toBeInTheDocument();
    expect(screen.getByText('Previous: 100')).toBeInTheDocument();
  });

  it('shows the absolute and percentage change', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }]);
    expect(screen.getByText(/\+10.*\(\+10.*%\)/)).toBeInTheDocument();
  });

  it('shows a bullish badge for a rising trend indicator (generic fallback)', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }]);
    expect(screen.getByText('Bullish')).toBeInTheDocument();
  });

  it('shows a bearish badge for a falling trend indicator (generic fallback)', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [110, 100] }]);
    expect(screen.getByText('Bearish')).toBeInTheDocument();
  });

  it('uses RSI-specific thresholds instead of the trend fallback', () => {
    // Rising into overbought territory — the threshold, not the direction,
    // must win for an indicator with its own convention.
    renderSummary([{ name: 'rsi', label: 'RSI(14)', values: [60, 75] }], 'rsi');
    expect(screen.getByText('Bearish')).toBeInTheDocument();
  });

  it('renders one card per series', () => {
    renderSummary([
      { name: 'upper', label: 'Upper', values: [10, 12] },
      { name: 'lower', label: 'Lower', values: [1, 2] },
    ]);
    expect(screen.getByText('Upper')).toBeInTheDocument();
    expect(screen.getByText('Lower')).toBeInTheDocument();
  });

  it('shows an em dash and no change badge when there is only one value', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [null, null, 5] }]);
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Previous: —')).toBeInTheDocument();
    expect(screen.queryByText('Bullish')).not.toBeInTheDocument();
    expect(screen.queryByText('Bearish')).not.toBeInTheDocument();
    expect(screen.queryByText('Neutral')).not.toBeInTheDocument();
  });

  it('exposes a field-info tooltip on the latest value', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }]);
    expect(screen.getByRole('button', { name: 'About Latest SMA(2)' })).toBeInTheDocument();
  });
});
