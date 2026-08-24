import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { RecentCalculation } from '../lib/recent-calculations';
import { RecentCalculationsPanel } from './recent-calculations-panel';

afterEach(() => {
  cleanup();
});

function entry(overrides: Partial<RecentCalculation> = {}): RecentCalculation {
  return {
    symbol: 'ETHUSD',
    indicator: 'sma',
    indicatorLabel: 'Simple Moving Average',
    timeframe: '1h',
    params: { period: '20' },
    timestamp: Date.UTC(2026, 0, 1, 12, 0),
    ...overrides,
  };
}

function renderPanel(entries: RecentCalculation[], onRerun = vi.fn()) {
  return {
    onRerun,
    ...render(
      <ThemeProvider theme={theme}>
        <RecentCalculationsPanel entries={entries} onRerun={onRerun} />
      </ThemeProvider>,
    ),
  };
}

describe('RecentCalculationsPanel', () => {
  it('explains that the list is empty rather than showing nothing', () => {
    renderPanel([]);
    expect(screen.getByText(/will appear here/)).toBeInTheDocument();
  });

  it('lists indicator, market, and timeframe for each entry', () => {
    renderPanel([entry()]);
    expect(screen.getByText('Simple Moving Average · ETHUSD · 1h')).toBeInTheDocument();
  });

  it('lists the parameters used', () => {
    renderPanel([entry({ params: { period: '50', source: 'high' } })]);
    expect(screen.getByText(/period=50, source=high/)).toBeInTheDocument();
  });

  it('says "default parameters" for an entry with none', () => {
    renderPanel([entry({ params: {} })]);
    expect(screen.getByText(/default parameters/)).toBeInTheDocument();
  });

  it('reruns the entry when its row is clicked', () => {
    const onRerun = vi.fn();
    renderPanel([entry()], onRerun);
    fireEvent.click(screen.getByText('Simple Moving Average · ETHUSD · 1h'));
    expect(onRerun).toHaveBeenCalledWith(entry());
  });

  it('reruns the entry via its dedicated rerun button', () => {
    const onRerun = vi.fn();
    renderPanel([entry()], onRerun);
    fireEvent.click(screen.getByRole('button', { name: 'Rerun Simple Moving Average on ETHUSD' }));
    expect(onRerun).toHaveBeenCalledWith(entry());
  });
});
