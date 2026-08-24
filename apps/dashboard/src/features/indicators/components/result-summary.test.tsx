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
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period parameter.',
    parameters: [],
    outputs: [],
  };
}

function renderSummary(series: IndicatorSeries[], indicatorName = 'sma', currentPrice?: number) {
  return render(
    <ThemeProvider theme={theme}>
      <ResultSummary
        series={series}
        knowledge={getIndicatorKnowledge(catalogueEntry(indicatorName))}
        currentPrice={currentPrice}
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

  it('shows no state badge for a plain trend indicator — a rising average is not a trading signal', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }]);
    expect(screen.queryByText('Bullish')).not.toBeInTheDocument();
    expect(screen.queryByText('Bearish')).not.toBeInTheDocument();
    // Trend direction is still reported, just not dressed up as a signal.
    expect(screen.getByTestId('ArrowUpwardIcon')).toBeInTheDocument();
  });

  it('shows an Overbought state badge for RSI above its own threshold', () => {
    // Rising into overbought territory — the threshold, not the
    // direction, drives the reading for an indicator with its own
    // convention; the label itself is a descriptive state, not "Bearish".
    renderSummary([{ name: 'rsi', label: 'RSI(14)', values: [60, 75] }], 'rsi');
    expect(screen.getByText('Overbought')).toBeInTheDocument();
  });

  it('shows an Oversold state badge for RSI below its own threshold', () => {
    renderSummary([{ name: 'rsi', label: 'RSI(14)', values: [40, 25] }], 'rsi');
    expect(screen.getByText('Oversold')).toBeInTheDocument();
  });

  it('renders one card per series', () => {
    renderSummary([
      { name: 'upper', label: 'Upper', values: [10, 12] },
      { name: 'lower', label: 'Lower', values: [1, 2] },
    ]);
    expect(screen.getByText('Upper')).toBeInTheDocument();
    expect(screen.getByText('Lower')).toBeInTheDocument();
  });

  it('shows an em dash and no state badge when there is only one value', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [null, null, 5] }]);
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Previous: —')).toBeInTheDocument();
    expect(screen.queryByText('Overbought')).not.toBeInTheDocument();
    expect(screen.queryByText('Oversold')).not.toBeInTheDocument();
  });

  it('exposes a field-info tooltip on the latest value', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }]);
    expect(screen.getByRole('button', { name: 'About Latest SMA(2)' })).toBeInTheDocument();
  });

  it('reports status as computed once a value exists', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }]);
    expect(screen.getByText('Status: Computed')).toBeInTheDocument();
  });

  it('reports status as warming-up when the series has no value yet', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [null, null] }]);
    expect(screen.getByText('Status: Warming up')).toBeInTheDocument();
  });

  it('shows no current-price row when no price is supplied', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }]);
    expect(screen.queryByText(/Current Price/)).not.toBeInTheDocument();
  });

  it('shows the current price and distance from it when supplied', () => {
    renderSummary([{ name: 'sma', label: 'SMA(2)', values: [100, 110] }], 'sma', 120);
    expect(screen.getByText(/Current Price: 120/)).toBeInTheDocument();
    expect(screen.getByText(/Distance: -10/)).toBeInTheDocument();
  });
});
