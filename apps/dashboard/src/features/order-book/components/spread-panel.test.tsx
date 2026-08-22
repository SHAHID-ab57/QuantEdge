import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { SpreadSummary } from '../lib/order-book-depth';
import { SpreadPanel } from './spread-panel';

afterEach(() => {
  cleanup();
});

function renderPanel(spread: SpreadSummary) {
  return render(
    <ThemeProvider theme={theme}>
      <SpreadPanel spread={spread} />
    </ThemeProvider>,
  );
}

describe('SpreadPanel', () => {
  it('renders best bid, best ask, spread, spread percent, and mid price', () => {
    renderPanel({ bestBid: 100, bestAsk: 101, spread: 1, spreadPercent: 0.995, midPrice: 100.5 });
    expect(screen.getByText('Best Bid')).toBeInTheDocument();
    expect(screen.getByText('100.00')).toBeInTheDocument();
    expect(screen.getByText('Best Ask')).toBeInTheDocument();
    expect(screen.getByText('101.00')).toBeInTheDocument();
    expect(screen.getByText('1.00')).toBeInTheDocument(); // spread
    expect(screen.getByText('0.995%')).toBeInTheDocument();
    expect(screen.getByText('100.50')).toBeInTheDocument(); // mid price
  });

  it('shows Unavailable for the missing side while still showing the present one', () => {
    renderPanel({ bestBid: null, bestAsk: 101, spread: null, spreadPercent: null, midPrice: null });
    expect(screen.getByText('101.00')).toBeInTheDocument(); // best ask still renders
    expect(screen.getAllByText('Unavailable')).toHaveLength(4); // best bid, spread, spread %, mid
  });

  it('shows Unavailable for every field when the book is empty', () => {
    renderPanel({
      bestBid: null,
      bestAsk: null,
      spread: null,
      spreadPercent: null,
      midPrice: null,
    });
    expect(screen.getAllByText('Unavailable')).toHaveLength(5);
  });
});
