import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { SessionStats } from '../lib/session-stats';
import { StatsCards } from './stats-cards';

afterEach(() => {
  cleanup();
});

function stats(overrides: Partial<SessionStats> = {}): SessionStats {
  return {
    buyVolume: 10,
    sellVolume: 5,
    totalVolume: 15,
    buySellRatio: 2,
    avgTradeSize: 3,
    largestTrade: { price: 100, size: 5, value: 500, side: 'buy', timestampMs: 0 },
    tradeCount: 5,
    sessionVwap: 105,
    avgTradeValue: 150,
    lastPrice: 105,
    lastSide: 'buy',
    sessionHigh: 110,
    sessionLow: 100,
    ...overrides,
  };
}

function renderCards(overrides: Partial<SessionStats> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <StatsCards stats={stats(overrides)} />
    </ThemeProvider>,
  );
}

describe('StatsCards', () => {
  it('renders every required stat', () => {
    renderCards();
    for (const label of [
      'Buy Volume',
      'Sell Volume',
      'Total Volume',
      'Buy/Sell Ratio',
      'Average Trade Size',
      'Number of Trades',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('shows buy/sell volumes and the total', () => {
    renderCards({ buyVolume: 10, sellVolume: 7, totalVolume: 17 });
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('17')).toBeInTheDocument();
  });

  it('shows a buy/sell pressure bar reflecting the session volumes', () => {
    renderCards({ buyVolume: 3, sellVolume: 1 });
    expect(screen.getByText('75% / 25%')).toBeInTheDocument();
  });

  it('says Unavailable for the ratio rather than Infinity when there is no sell volume', () => {
    renderCards({ buySellRatio: null });
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
  });

  it('says Unavailable for an empty session (no trades yet)', () => {
    renderCards({
      buyVolume: 0,
      sellVolume: 0,
      totalVolume: 0,
      buySellRatio: null,
      avgTradeSize: null,
      largestTrade: null,
      tradeCount: 0,
      sessionVwap: null,
      avgTradeValue: null,
    });
    // Ratio, average trade size, and the pressure bar's percentage text are all Unavailable.
    expect(screen.getAllByText('Unavailable')).toHaveLength(3);
  });
});
