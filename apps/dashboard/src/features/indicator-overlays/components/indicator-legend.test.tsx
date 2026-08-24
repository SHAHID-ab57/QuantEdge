import { ThemeProvider } from '@mui/material/styles';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { OverlayChartSeries } from '../lib/overlay-series';
import { useOverlayStore, type OverlayConfig } from '../store/use-overlay-store';
import { IndicatorLegend } from './indicator-legend';

function overlay(overrides: Partial<OverlayConfig> = {}): OverlayConfig {
  return {
    id: 'overlay-1',
    indicator: 'sma',
    label: 'SMA(20)',
    params: { period: '20' },
    enabled: true,
    colorIndex: 0,
    ...overrides,
  };
}

function series(overrides: Partial<OverlayChartSeries> = {}): OverlayChartSeries {
  return {
    id: 'overlay-1',
    label: 'SMA(20)',
    color: '#2196f3',
    data: [],
    ok: true,
    meta: {
      cacheStatus: 'hit',
      warmupCandles: 19,
      executionTimeMs: 0.08,
      candlesAnalyzed: 500,
      generatedAt: '2026-01-01T00:00:00Z',
      engineVersion: '1.0.0',
      sourceParam: 'close',
    },
    ...overrides,
  };
}

function renderLegend(
  overlays: OverlayConfig[],
  props: Partial<React.ComponentProps<typeof IndicatorLegend>> = {},
) {
  return render(
    <ThemeProvider theme={theme}>
      <IndicatorLegend overlays={overlays} {...props} />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  act(() => useOverlayStore.getState().clearOverlays());
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe('IndicatorLegend', () => {
  it('says there are no overlays when the list is empty', () => {
    renderLegend([]);
    expect(screen.getByText(/No indicator overlays added/)).toBeInTheDocument();
  });

  it('shows the name and resolved parameters for each overlay', () => {
    renderLegend([overlay()]);
    expect(screen.getByText('SMA(20)')).toBeInTheDocument();
    expect(screen.getByText('period=20')).toBeInTheDocument();
  });

  it('says "default parameters" for an overlay with none', () => {
    renderLegend([overlay({ params: {} })]);
    expect(screen.getByText('default parameters')).toBeInTheDocument();
  });

  it('renders one entry per overlay', () => {
    renderLegend([
      overlay({ id: 'a', label: 'SMA(20)' }),
      overlay({ id: 'b', label: 'EMA(20)', colorIndex: 1 }),
    ]);
    expect(screen.getByText('SMA(20)')).toBeInTheDocument();
    expect(screen.getByText('EMA(20)')).toBeInTheDocument();
  });

  it('toggles visibility via the store when the hide/show button is clicked', () => {
    act(() => {
      useOverlayStore.setState({ overlays: [overlay()], nextColorIndex: 1 });
    });
    renderLegend(useOverlayStore.getState().overlays);
    fireEvent.click(screen.getByRole('button', { name: 'Hide SMA(20)' }));
    expect(useOverlayStore.getState().overlays[0]!.enabled).toBe(false);
  });

  it('removes the overlay via the store when the remove button is clicked', () => {
    act(() => {
      useOverlayStore.setState({ overlays: [overlay()], nextColorIndex: 1 });
    });
    renderLegend(useOverlayStore.getState().overlays);
    fireEvent.click(screen.getByRole('button', { name: 'Remove SMA(20)' }));
    expect(useOverlayStore.getState().overlays).toHaveLength(0);
  });

  it('visually dims a disabled overlay', () => {
    renderLegend([overlay({ enabled: false })]);
    const label = screen.getByText('SMA(20)');
    const row = label.closest('div');
    expect(row).toHaveStyle({ opacity: '0.5' });
  });

  describe('reordering', () => {
    it('disables "move up" for the first overlay and "move down" for the last', () => {
      act(() => {
        useOverlayStore.setState({
          overlays: [
            overlay({ id: 'a', label: 'SMA(20)' }),
            overlay({ id: 'b', label: 'EMA(20)' }),
          ],
          nextColorIndex: 2,
        });
      });
      renderLegend(useOverlayStore.getState().overlays);
      expect(screen.getByRole('button', { name: 'Move SMA(20) up' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Move EMA(20) down' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Move SMA(20) down' })).not.toBeDisabled();
      expect(screen.getByRole('button', { name: 'Move EMA(20) up' })).not.toBeDisabled();
    });

    it('moves an overlay down via the store when its down arrow is clicked', () => {
      act(() => {
        useOverlayStore.setState({
          overlays: [
            overlay({ id: 'a', label: 'SMA(20)' }),
            overlay({ id: 'b', label: 'EMA(20)' }),
          ],
          nextColorIndex: 2,
        });
      });
      renderLegend(useOverlayStore.getState().overlays);
      fireEvent.click(screen.getByRole('button', { name: 'Move SMA(20) down' }));
      expect(useOverlayStore.getState().overlays.map((o) => o.id)).toEqual(['b', 'a']);
    });
  });

  describe('calculation details', () => {
    it('shows a loading indicator per row while a batch calculation is in flight', () => {
      renderLegend([overlay()], { overlaySeries: [series()], isLoading: true });
      expect(screen.getByLabelText('Recalculating')).toBeInTheDocument();
    });

    it('flags a failed overlay without hiding the row', () => {
      renderLegend([overlay()], {
        overlaySeries: [series({ ok: false, error: 'Insufficient data.' })],
        isLoading: false,
      });
      expect(screen.getByText('SMA(20)')).toBeInTheDocument();
      expect(screen.getByText('Error')).toBeInTheDocument();
    });

    it('exposes calculation metadata via the details info button', () => {
      renderLegend([overlay()], { overlaySeries: [series()] });
      expect(
        screen.getByRole('button', { name: 'About SMA(20) calculation details' }),
      ).toBeInTheDocument();
    });
  });

  describe('export', () => {
    it('offers no export action without a symbol/timeframe', () => {
      renderLegend([overlay()]);
      expect(screen.queryByRole('button', { name: 'Export overlays' })).not.toBeInTheDocument();
    });

    it('offers export once a symbol/timeframe are supplied', () => {
      renderLegend([overlay()], { symbol: 'ETHUSD', timeframe: '1h', overlaySeries: [series()] });
      expect(screen.getByRole('button', { name: 'Export overlays' })).toBeInTheDocument();
    });
  });
});
