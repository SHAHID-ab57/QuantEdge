import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { MetricHistory } from '../lib/metric-history';
import type { VwapSet } from '../lib/rolling-window';
import { VwapPanel } from './vwap-panel';

afterEach(() => {
  cleanup();
});

function history(overrides: Partial<MetricHistory> = {}): MetricHistory {
  return {
    timestamps: [],
    buyVolume: [],
    sellVolume: [],
    tradesPerMinute: [],
    volumePerMinute: [],
    vwapOneMinute: [],
    avgTradeSize: [],
    ...overrides,
  };
}

function renderPanel(vwap: VwapSet, historyOverrides: Partial<MetricHistory> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <VwapPanel vwap={vwap} history={history(historyOverrides)} />
    </ThemeProvider>,
  );
}

describe('VwapPanel', () => {
  it('renders all four VWAP figures', () => {
    renderPanel({ session: 100, oneMinute: 101, fiveMinute: 102, fifteenMinute: 103 });
    expect(screen.getByText('Session VWAP')).toBeInTheDocument();
    expect(screen.getByText('100.00')).toBeInTheDocument();
    expect(screen.getByText('1m VWAP')).toBeInTheDocument();
    expect(screen.getByText('101.00')).toBeInTheDocument();
    expect(screen.getByText('5m VWAP')).toBeInTheDocument();
    expect(screen.getByText('102.00')).toBeInTheDocument();
    expect(screen.getByText('15m VWAP')).toBeInTheDocument();
    expect(screen.getByText('103.00')).toBeInTheDocument();
  });

  it('says Unavailable for a window with no trades rather than a placeholder dash', () => {
    renderPanel({ session: null, oneMinute: null, fiveMinute: null, fifteenMinute: null });
    expect(screen.getAllByText('Unavailable')).toHaveLength(4);
  });

  it('can report the session VWAP while rolling windows are still empty', () => {
    renderPanel({ session: 100, oneMinute: null, fiveMinute: null, fifteenMinute: null });
    expect(screen.getByText('100.00')).toBeInTheDocument();
    expect(screen.getAllByText('Unavailable')).toHaveLength(3);
  });

  it('renders a rolling VWAP sparkline from the metric history', () => {
    renderPanel(
      { session: 100, oneMinute: 101, fiveMinute: 102, fifteenMinute: 103 },
      { vwapOneMinute: [99, 100, 101] },
    );
    expect(screen.getByRole('img', { name: 'Rolling 1-minute VWAP trend' })).toBeInTheDocument();
  });
});
