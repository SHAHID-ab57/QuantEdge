import { render, cleanup } from '@testing-library/react';
import type { UTCTimestamp } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CandlestickChart } from './candlestick-chart';

function utc(seconds: number): UTCTimestamp {
  return seconds as UTCTimestamp;
}

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
let fitContent: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  candleSeries = fakeSeries();
  volumeSeries = fakeSeries();
  fitContent = vi.fn();
  fakeChart.timeScale.mockReturnValue({ fitContent });
  // The component always adds the candlestick series first, then volume.
  let call = 0;
  fakeChart.addSeries.mockImplementation(() => {
    call += 1;
    return call === 1 ? candleSeries : volumeSeries;
  });
});

afterEach(() => {
  cleanup();
});

const candlesticks = [
  { time: utc(1_785_888_000), open: 100, high: 110, low: 90, close: 105 },
  { time: utc(1_785_891_600), open: 105, high: 115, low: 95, close: 108 },
];
const volume = [
  { time: utc(1_785_888_000), value: 10, color: '#22c55e' },
  { time: utc(1_785_891_600), value: 12, color: '#22c55e' },
];

describe('CandlestickChart', () => {
  it('creates the chart and both series on mount, and fits content', () => {
    render(<CandlestickChart candlesticks={candlesticks} volume={volume} />);

    expect(createChartMock).toHaveBeenCalledTimes(1);
    expect(fakeChart.addSeries).toHaveBeenCalledTimes(2);
    expect(candleSeries.setData).toHaveBeenCalledWith(candlesticks);
    expect(volumeSeries.setData).toHaveBeenCalledWith(volume);
    expect(fitContent).toHaveBeenCalled();
  });

  it('pushes new data into the existing series without recreating the chart', () => {
    const { rerender } = render(<CandlestickChart candlesticks={candlesticks} volume={volume} />);
    expect(createChartMock).toHaveBeenCalledTimes(1);

    const nextCandlesticks = [
      ...candlesticks,
      { time: utc(1_785_895_200), open: 108, high: 112, low: 104, close: 110 },
    ];
    rerender(<CandlestickChart candlesticks={nextCandlesticks} volume={volume} />);

    expect(createChartMock).toHaveBeenCalledTimes(1);
    expect(candleSeries.setData).toHaveBeenLastCalledWith(nextCandlesticks);
  });

  it('re-fits content when fitContentToken changes without re-pushing data', () => {
    const { rerender } = render(
      <CandlestickChart candlesticks={candlesticks} volume={volume} fitContentToken={0} />,
    );
    const callsAfterMount = fitContent.mock.calls.length;

    rerender(<CandlestickChart candlesticks={candlesticks} volume={volume} fitContentToken={1} />);

    expect(fitContent.mock.calls.length).toBeGreaterThan(callsAfterMount);
  });

  it('subscribes to crosshair moves and reports OHLCV at the hovered time', () => {
    const onCrosshairMove = vi.fn();
    render(
      <CandlestickChart
        candlesticks={candlesticks}
        volume={volume}
        onCrosshairMove={onCrosshairMove}
      />,
    );

    expect(fakeChart.subscribeCrosshairMove).toHaveBeenCalledTimes(1);
    const handler = fakeChart.subscribeCrosshairMove.mock.calls[0]![0] as (param: unknown) => void;

    const seriesData = new Map([
      [candleSeries, { open: 100, high: 110, low: 90, close: 105 }],
      [volumeSeries, { value: 10 }],
    ]);
    handler({ time: 1_785_888_000, seriesData });
    expect(onCrosshairMove).toHaveBeenCalledWith({
      time: 1_785_888_000,
      open: 100,
      high: 110,
      low: 90,
      close: 105,
      volume: 10,
    });

    handler({ time: undefined, seriesData: new Map() });
    expect(onCrosshairMove).toHaveBeenLastCalledWith(null);
  });

  it('removes the chart on unmount', () => {
    const { unmount } = render(<CandlestickChart candlesticks={candlesticks} volume={volume} />);
    unmount();
    expect(fakeChart.remove).toHaveBeenCalledTimes(1);
  });

  it('pushes a live candle/volume update via series.update(), not setData()', () => {
    const liveBar = { time: utc(1_785_895_200), open: 108, high: 112, low: 104, close: 110 };
    const liveVol = { time: utc(1_785_895_200), value: 5, color: '#22c55e' };
    const { rerender } = render(<CandlestickChart candlesticks={candlesticks} volume={volume} />);
    candleSeries.setData.mockClear();
    volumeSeries.setData.mockClear();

    rerender(
      <CandlestickChart
        candlesticks={candlesticks}
        volume={volume}
        liveCandle={liveBar}
        liveVolume={liveVol}
      />,
    );

    expect(candleSeries.update).toHaveBeenCalledWith(liveBar);
    expect(volumeSeries.update).toHaveBeenCalledWith(liveVol);
    expect(candleSeries.setData).not.toHaveBeenCalled();
    expect(volumeSeries.setData).not.toHaveBeenCalled();
  });

  it('does not call update() when no live candle is provided', () => {
    render(<CandlestickChart candlesticks={candlesticks} volume={volume} />);
    expect(candleSeries.update).not.toHaveBeenCalled();
    expect(volumeSeries.update).not.toHaveBeenCalled();
  });

  it('drops a live update older than the newest data already in the series', () => {
    // Reachable in normal operation: a historical refetch can land while a
    // forming bar for an earlier bucket is still on screen. lightweight-charts
    // throws on an out-of-order update(), so it must be skipped, not passed on.
    const staleBar = { time: utc(1_700_000_000), open: 1, high: 2, low: 0, close: 1 };
    const { rerender } = render(<CandlestickChart candlesticks={candlesticks} volume={volume} />);
    candleSeries.update.mockClear();

    rerender(
      <CandlestickChart candlesticks={candlesticks} volume={volume} liveCandle={staleBar} />,
    );

    expect(candleSeries.update).not.toHaveBeenCalled();
  });
});
