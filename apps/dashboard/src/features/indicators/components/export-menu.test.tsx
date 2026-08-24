import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { IndicatorCalculation } from '@/types/api/indicators';
import { ExportMenu } from './export-menu';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function result(overrides: Partial<IndicatorCalculation> = {}): IndicatorCalculation {
  return {
    symbol: 'ETHUSD',
    timeframe: '1h',
    indicator: {
      name: 'sma',
      label: 'Simple Moving Average',
      description: 'Stub.',
      category: 'trend',
      parameters: [],
      outputs: [],
    },
    parameters: { period: 20, source: 'close' },
    timestamps: ['2026-01-01T00:00:00Z'],
    series: [{ name: 'sma', label: 'SMA(20)', values: [3055.25] }],
    meta: {
      candles_analyzed: 1,
      warmup_candles: 0,
      execution_time_ms: 0.1,
      database_time_ms: 1,
      cache_status: 'miss',
      generated_at: '2026-01-01T02:00:00Z',
    },
    ...overrides,
  };
}

function renderMenu(overrides: Partial<IndicatorCalculation> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <ExportMenu result={result(overrides)} />
    </ThemeProvider>,
  );
}

function openMenu() {
  fireEvent.click(screen.getByRole('button', { name: 'Export' }));
}

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  URL.createObjectURL = vi.fn().mockReturnValue('blob:mock');
  URL.revokeObjectURL = vi.fn();
});

describe('ExportMenu', () => {
  it('opens a menu listing every export action', () => {
    renderMenu();
    openMenu();
    expect(screen.getByRole('menuitem', { name: 'Export CSV' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Export JSON' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Copy Values' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Copy API Request' })).toBeInTheDocument();
  });

  it('triggers a CSV download via an object URL', () => {
    renderMenu();
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Export CSV' }));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock');
  });

  it('triggers a JSON download', () => {
    renderMenu();
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Export JSON' }));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  it('copies the values table to the clipboard and confirms it', async () => {
    renderMenu();
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy Values' }));
    expect(await screen.findByText('Values copied to clipboard')).toBeInTheDocument();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining('SMA(20)'));
  });

  it('copies the literal API request URL to the clipboard', async () => {
    renderMenu();
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy API Request' }));
    expect(await screen.findByText('API request copied to clipboard')).toBeInTheDocument();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/markets/ETHUSD/indicators/sma'),
    );
  });

  it('reports when the clipboard is unavailable rather than failing silently', async () => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    });
    renderMenu();
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy Values' }));
    expect(await screen.findByText('Could not access the clipboard')).toBeInTheDocument();
  });

  it('closes the menu after an action', () => {
    renderMenu();
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Export CSV' }));
    expect(screen.queryByRole('menuitem', { name: 'Export CSV' })).not.toBeInTheDocument();
  });
});
