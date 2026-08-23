import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { MetricHistory } from '../lib/metric-history';
import type { RollingAnalytics } from '../lib/rolling-window';
import { RollingAnalyticsPanel } from './rolling-analytics-panel';

afterEach(() => {
  cleanup();
});

function analytics(overrides: Partial<RollingAnalytics> = {}): RollingAnalytics {
  return {
    tradesPerMinute: 12,
    volumePerMinute: 34,
    tradesPerSecond: 0.2,
    buyVolume: 20,
    sellVolume: 14,
    avgTradeSize: 2.8,
    largestTrade: { price: 100, size: 5, value: 500, side: 'buy', timestampMs: 0 },
    buySellImbalance: 0.25,
    ...overrides,
  };
}

function emptyHistory(): MetricHistory {
  return {
    timestamps: [],
    buyVolume: [],
    sellVolume: [],
    tradesPerMinute: [],
    volumePerMinute: [],
    vwapOneMinute: [],
    avgTradeSize: [],
  };
}

function renderPanel(
  overrides: Partial<RollingAnalytics> = {},
  historyOverrides: Partial<MetricHistory> = {},
) {
  return render(
    <ThemeProvider theme={theme}>
      <RollingAnalyticsPanel
        rolling={analytics(overrides)}
        history={{ ...emptyHistory(), ...historyOverrides }}
      />
    </ThemeProvider>,
  );
}

describe('RollingAnalyticsPanel', () => {
  it('renders trades/minute, volume/minute, average size, and imbalance', () => {
    renderPanel();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('34')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument(); // avg trade size rounded
    expect(screen.getByText('+25%')).toBeInTheDocument();
  });

  it('formats a negative imbalance with a minus sign, not a double sign', () => {
    renderPanel({ buySellImbalance: -0.5 });
    expect(screen.getByText('-50%')).toBeInTheDocument();
  });

  it('formats a perfectly balanced window as 0%, not +0%', () => {
    renderPanel({ buySellImbalance: 0 });
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('says Unavailable across the board for an empty window', () => {
    renderPanel({
      tradesPerMinute: 0,
      volumePerMinute: 0,
      buyVolume: 0,
      sellVolume: 0,
      avgTradeSize: null,
      largestTrade: null,
      buySellImbalance: null,
    });
    expect(screen.getAllByText('0')).toHaveLength(2); // trades/minute and volume/minute, both a real zero
    // Average trade size and imbalance are Unavailable.
    expect(screen.getAllByText('Unavailable')).toHaveLength(2);
  });

  it('renders sparklines for trades/minute, volume/minute, average size, and buy/sell volume', () => {
    renderPanel(
      {},
      {
        tradesPerMinute: [1, 2, 3],
        volumePerMinute: [4, 5, 6],
        avgTradeSize: [1, 2, 1],
        buyVolume: [1, 2, 3],
        sellVolume: [3, 2, 1],
      },
    );
    expect(screen.getByRole('img', { name: 'Trades per minute trend' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Volume per minute trend' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Average trade size trend' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Buy volume trend' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Sell volume trend' })).toBeInTheDocument();
  });

  it('renders a placeholder sparkline (not a crash) when there is no history sample yet', () => {
    renderPanel();
    expect(
      screen.getByRole('img', { name: 'Trades per minute trend: not enough data yet' }),
    ).toBeInTheDocument();
  });
});
