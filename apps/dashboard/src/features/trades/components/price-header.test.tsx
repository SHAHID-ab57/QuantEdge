import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { SessionStats } from '../lib/session-stats';
import type { VwapDistance } from '../lib/vwap-distance';
import { PriceHeader } from './price-header';

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
    largestTrade: null,
    tradeCount: 5,
    sessionVwap: 100,
    avgTradeValue: 150,
    lastPrice: 105,
    lastSide: 'buy',
    sessionHigh: 110,
    sessionLow: 95,
    ...overrides,
  };
}

function renderHeader(
  overrides: Partial<SessionStats> = {},
  vwapDistance: VwapDistance | null = { absolute: 5, fraction: 0.05 },
  tradesPerSecond = 1.5,
  isLive = true,
) {
  return render(
    <ThemeProvider theme={theme}>
      <PriceHeader
        symbol="ETHUSD"
        stats={stats(overrides)}
        vwapDistance={vwapDistance}
        tradesPerSecond={tradesPerSecond}
        isLive={isLive}
      />
    </ThemeProvider>,
  );
}

describe('PriceHeader', () => {
  it('shows the current price, session high, and session low', () => {
    renderHeader();
    expect(screen.getByText('105.00')).toBeInTheDocument();
    expect(screen.getByText('110.00')).toBeInTheDocument();
    expect(screen.getByText('95.00')).toBeInTheDocument();
  });

  it('names the symbol in the region label so a screen reader knows which market it is', () => {
    renderHeader();
    expect(screen.getByRole('status', { name: 'ETHUSD price summary' })).toBeInTheDocument();
  });

  it('shows a positive VWAP distance with an explicit plus sign', () => {
    renderHeader({}, { absolute: 5, fraction: 0.05 });
    expect(screen.getByText('+5.00%')).toBeInTheDocument();
  });

  it('shows a negative VWAP distance without doubling the sign', () => {
    renderHeader({}, { absolute: -5, fraction: -0.05 });
    expect(screen.getByText('-5.00%')).toBeInTheDocument();
  });

  it('shows the live trades-per-second rate', () => {
    renderHeader({}, null, 2.4);
    expect(screen.getByText('2.4/s')).toBeInTheDocument();
  });

  it('reports Idle rather than a rate when connected but nothing is printing', () => {
    renderHeader({}, null, 0, true);
    expect(screen.getByText('Idle')).toBeInTheDocument();
  });

  it('says Unavailable for activity when the stream is not live at all', () => {
    renderHeader({}, null, 0, false);
    const header = screen.getByRole('status', { name: 'ETHUSD price summary' });
    expect(within(header).getAllByText('Unavailable').length).toBeGreaterThan(0);
  });

  it('says Unavailable across the board before the first trade', () => {
    renderHeader(
      { lastPrice: null, lastSide: null, sessionHigh: null, sessionLow: null, sessionVwap: null },
      null,
      0,
      true,
    );
    // Current price, session high, session low, and VWAP distance.
    expect(screen.getAllByText('Unavailable')).toHaveLength(4);
  });

  it('offers a contextual explanation for every metric in the band', () => {
    renderHeader();
    for (const label of [
      'About Current Price',
      'About Session High',
      'About Session Low',
      'About Distance from VWAP',
      'About Trades per second',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });
});
