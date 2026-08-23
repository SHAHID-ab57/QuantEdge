import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { computeSizeDistribution } from '../lib/size-distribution';
import type { TradeRecord } from '../lib/trade-record';
import { TradeSizeDistribution } from './trade-size-distribution';

afterEach(() => {
  cleanup();
});

const NOW = 600_000;

function record(size: number, index: number): TradeRecord {
  return { price: 100, size, value: 100 * size, side: 'buy', timestampMs: NOW - index * 100 };
}

function renderDistribution(sizes: number[]) {
  const records = sizes.map((size, index) => record(size, index)).reverse();
  return render(
    <ThemeProvider theme={theme}>
      <TradeSizeDistribution distribution={computeSizeDistribution(records, NOW)} />
    </ThemeProvider>,
  );
}

describe('TradeSizeDistribution', () => {
  it('renders one labelled bar per bucket', () => {
    renderDistribution([1, 2, 3]);
    for (const label of ['<0.5×', '0.5–1×', '1–2×', '2–5×', '≥5×']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByRole('meter')).toHaveLength(5);
  });

  it('says there are no trades yet for an empty window, rather than showing a misleading 0%', () => {
    renderDistribution([]);
    expect(screen.getByText('no trades yet')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(5);
  });

  it('reports the number of trades the distribution covers', () => {
    renderDistribution([1, 2, 3, 4]);
    expect(screen.getByText('4 trades')).toBeInTheDocument();
  });

  it('describes each bar for a screen reader with both a percentage and a raw count', () => {
    renderDistribution([1, 1, 1, 1, 1, 1, 1, 1, 1, 100]);
    const tail = screen.getByRole('meter', { name: 'Trades between ≥5× of average size' });
    expect(tail).toHaveAttribute('aria-valuetext', '10% of trades, 1 of 10');
  });

  it('offers a contextual explanation of what the distribution means', () => {
    renderDistribution([1, 2]);
    expect(
      screen.getByRole('button', { name: 'About Trade Size Distribution' }),
    ).toBeInTheDocument();
  });
});
