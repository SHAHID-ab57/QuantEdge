import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { Candle } from '@/types/api/market';
import type { ReplayClockTick } from '../engine/replay-clock';
import { ReplayChart } from './replay-chart';

const fakeSeries = () => ({
  setData: vi.fn(),
  update: vi.fn(),
  applyOptions: vi.fn(),
  priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
});

const fakeChart = vi.hoisted(() => ({
  addSeries: vi.fn(),
  applyOptions: vi.fn(),
  remove: vi.fn(),
  timeScale: vi.fn(),
  subscribeCrosshairMove: vi.fn(),
  unsubscribeCrosshairMove: vi.fn(),
}));

const createChartMock = vi.hoisted(() => vi.fn(() => fakeChart));

vi.mock('lightweight-charts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lightweight-charts')>();
  return { ...actual, createChart: createChartMock };
});

let candleSeries: ReturnType<typeof fakeSeries>;
let volumeSeries: ReturnType<typeof fakeSeries>;

beforeEach(() => {
  vi.clearAllMocks();
  candleSeries = fakeSeries();
  volumeSeries = fakeSeries();
  fakeChart.timeScale.mockReturnValue({ fitContent: vi.fn() });
  let call = 0;
  fakeChart.addSeries.mockImplementation(() => {
    call += 1;
    return call === 1 ? candleSeries : volumeSeries;
  });
});

afterEach(() => {
  cleanup();
});

function candle(openTimeIso: string, close = '100'): Candle {
  return {
    open_time: openTimeIso,
    close_time: openTimeIso,
    open: '100',
    high: '100',
    low: '100',
    close,
    volume: '5',
    source: 'test',
  };
}

const CANDLES = Array.from({ length: 5 }, (_, i) =>
  candle(`2026-01-01T00:0${i}:00Z`, String(100 + i)),
);

function tick(overrides: Partial<ReplayClockTick> = {}): ReplayClockTick {
  return {
    phase: 'paused',
    index: 2,
    candle: CANDLES[2] ?? null,
    timestampMs: Date.parse('2026-01-01T00:02:00Z'),
    speed: 1,
    isDiscontinuity: true,
    revealEpoch: 1,
    ...overrides,
  };
}

function renderChart(props: Partial<React.ComponentProps<typeof ReplayChart>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <ReplayChart candles={CANDLES} tick={tick()} isLoading={false} {...props} />
    </ThemeProvider>,
  );
}

describe('ReplayChart', () => {
  it('shows a loading skeleton while the session is loading', () => {
    renderChart({ isLoading: true, candles: [] });
    expect(screen.getByRole('status', { name: 'Loading replay chart' })).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it('creates the chart and seeds it up to the current index', () => {
    renderChart();
    expect(createChartMock).toHaveBeenCalledTimes(1);
    expect(candleSeries.setData).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ close: 100 })]),
    );
    expect(candleSeries.setData.mock.calls[0]?.[0]).toHaveLength(3); // indices 0, 1, 2
  });

  it('renders the legend for the current candle', () => {
    renderChart();
    // ChartLegend renders the close price of the current point.
    expect(screen.getByText('102.00', { exact: false })).toBeInTheDocument();
  });

  it('pushes subsequent candles incrementally via update(), not another setData()', () => {
    const { rerender } = renderChart({ tick: tick({ index: 2, revealEpoch: 1 }) });
    expect(candleSeries.setData).toHaveBeenCalledTimes(1);

    rerender(
      <ThemeProvider theme={theme}>
        <ReplayChart
          candles={CANDLES}
          tick={tick({ index: 3, revealEpoch: 1 })}
          isLoading={false}
        />
      </ThemeProvider>,
    );

    expect(candleSeries.setData).toHaveBeenCalledTimes(1); // still just the initial seed
    expect(candleSeries.update).toHaveBeenCalledWith(expect.objectContaining({ close: 103 }));
  });

  it('reseeds via setData() again after a discontinuous jump (revealEpoch bump)', () => {
    const { rerender } = renderChart({ tick: tick({ index: 4, revealEpoch: 1 }) });
    expect(candleSeries.setData).toHaveBeenCalledTimes(1);

    rerender(
      <ThemeProvider theme={theme}>
        <ReplayChart
          candles={CANDLES}
          tick={tick({ index: 0, revealEpoch: 2 })}
          isLoading={false}
        />
      </ThemeProvider>,
    );

    expect(candleSeries.setData).toHaveBeenCalledTimes(2);
  });
});
