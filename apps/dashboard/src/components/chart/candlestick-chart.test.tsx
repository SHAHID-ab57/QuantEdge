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
  removeSeries: vi.fn(),
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

let overlaySeriesInstances: ReturnType<typeof fakeSeries>[];

beforeEach(() => {
  vi.clearAllMocks();
  candleSeries = fakeSeries();
  volumeSeries = fakeSeries();
  overlaySeriesInstances = [];
  fitContent = vi.fn();
  fakeChart.timeScale.mockReturnValue({ fitContent });
  // The component always adds the candlestick series first, then volume;
  // any series requested after that is an overlay line, one per call.
  let call = 0;
  fakeChart.addSeries.mockImplementation(() => {
    call += 1;
    if (call === 1) return candleSeries;
    if (call === 2) return volumeSeries;
    const overlay = fakeSeries();
    overlaySeriesInstances.push(overlay);
    return overlay;
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

  describe('overlays (Overlay Engine)', () => {
    const overlayA = {
      id: 'sma-20',
      label: 'SMA(20)',
      color: '#2196f3',
      data: [{ time: utc(1_785_888_000), value: 101 }],
    };
    const overlayB = {
      id: 'ema-20',
      label: 'EMA(20)',
      color: '#ff9800',
      data: [{ time: utc(1_785_888_000), value: 102 }],
    };

    it('adds one line series per overlay and pushes its data', () => {
      render(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[overlayA]} />,
      );
      expect(fakeChart.addSeries).toHaveBeenCalledTimes(3); // candle + volume + one overlay
      expect(overlaySeriesInstances[0]!.setData).toHaveBeenCalledWith(overlayA.data);
    });

    it('adds a second overlay without touching the first', () => {
      const { rerender } = render(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[overlayA]} />,
      );
      const firstOverlaySeries = overlaySeriesInstances[0]!;
      firstOverlaySeries.setData.mockClear();

      rerender(
        <CandlestickChart
          candlesticks={candlesticks}
          volume={volume}
          overlays={[overlayA, overlayB]}
        />,
      );

      expect(overlaySeriesInstances).toHaveLength(2);
      // The existing overlay's series must not be recreated or re-pushed
      // just because a sibling was added.
      expect(fakeChart.removeSeries).not.toHaveBeenCalled();
      expect(firstOverlaySeries.setData).not.toHaveBeenCalled();
    });

    it('removes a series when its overlay is no longer present', () => {
      const { rerender } = render(
        <CandlestickChart
          candlesticks={candlesticks}
          volume={volume}
          overlays={[overlayA, overlayB]}
        />,
      );
      const removedSeries = overlaySeriesInstances[0]!;

      rerender(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[overlayB]} />,
      );

      expect(fakeChart.removeSeries).toHaveBeenCalledWith(removedSeries);
    });

    it('updates an existing overlay in place when its data reference changes', () => {
      const { rerender } = render(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[overlayA]} />,
      );
      const series = overlaySeriesInstances[0]!;
      const updated = { ...overlayA, data: [{ time: utc(1_785_888_000), value: 999 }] };

      rerender(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[updated]} />,
      );

      expect(fakeChart.addSeries).toHaveBeenCalledTimes(3); // no new series created
      expect(series.setData).toHaveBeenCalledWith(updated.data);
    });

    it('does not re-push an overlay whose data reference is unchanged', () => {
      const { rerender } = render(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[overlayA]} />,
      );
      const series = overlaySeriesInstances[0]!;
      series.setData.mockClear();

      // Same overlay, same `data` reference — re-render for an unrelated reason.
      rerender(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[overlayA]} />,
      );

      expect(series.setData).not.toHaveBeenCalled();
    });

    it('applies a color change to an existing series via applyOptions, not a new series', () => {
      const { rerender } = render(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[overlayA]} />,
      );
      const series = overlaySeriesInstances[0]!;
      const recolored = { ...overlayA, color: '#ff0000' };

      rerender(
        <CandlestickChart candlesticks={candlesticks} volume={volume} overlays={[recolored]} />,
      );

      expect(fakeChart.addSeries).toHaveBeenCalledTimes(3);
      expect(series.applyOptions).toHaveBeenCalledWith(
        expect.objectContaining({ color: '#ff0000' }),
      );
    });

    it('renders with no overlays by default', () => {
      render(<CandlestickChart candlesticks={candlesticks} volume={volume} />);
      expect(fakeChart.addSeries).toHaveBeenCalledTimes(2);
    });

    it('recreates every series in the new order when overlays are reordered, so paint order follows it', () => {
      const { rerender } = render(
        <CandlestickChart
          candlesticks={candlesticks}
          volume={volume}
          overlays={[overlayA, overlayB]}
        />,
      );
      const [firstSeries, secondSeries] = overlaySeriesInstances;
      expect(fakeChart.removeSeries).not.toHaveBeenCalled();

      // Same two overlays, reversed order — nothing added or removed.
      rerender(
        <CandlestickChart
          candlesticks={candlesticks}
          volume={volume}
          overlays={[overlayB, overlayA]}
        />,
      );

      // Both previous series are torn down and replaced so the new series
      // are added to the chart in the new (B, A) order.
      expect(fakeChart.removeSeries).toHaveBeenCalledWith(firstSeries);
      expect(fakeChart.removeSeries).toHaveBeenCalledWith(secondSeries);
      expect(overlaySeriesInstances).toHaveLength(4);
      const [, , thirdSeries, fourthSeries] = overlaySeriesInstances;
      expect(thirdSeries!.setData).toHaveBeenCalledWith(overlayB.data);
      expect(fourthSeries!.setData).toHaveBeenCalledWith(overlayA.data);
    });
  });
});
