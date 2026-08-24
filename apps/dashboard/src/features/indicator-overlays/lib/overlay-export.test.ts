import { describe, expect, it } from 'vitest';
import type { OverlayChartSeries } from './overlay-series';
import {
  buildOverlayCsv,
  buildOverlayJson,
  buildOverlayValuesText,
  overlayExportFileName,
} from './overlay-export';

function series(overrides: Partial<OverlayChartSeries> = {}): OverlayChartSeries {
  return {
    id: 'a',
    label: 'SMA(20)',
    color: '#2196f3',
    data: [
      { time: 1_735_689_600, value: 100 },
      { time: 1_735_693_200, value: 101 },
    ] as never,
    ok: true,
    ...overrides,
  };
}

describe('overlayExportFileName', () => {
  it('sanitizes the symbol and names the file by extension', () => {
    expect(overlayExportFileName('ETH/USD', 'csv')).toBe('ETH-USD-overlays.csv');
    expect(overlayExportFileName('ETHUSD', 'json')).toBe('ETHUSD-overlays.json');
  });
});

describe('buildOverlayCsv', () => {
  it('includes a metadata block and one column per successful overlay', () => {
    const csv = buildOverlayCsv({ symbol: 'ETHUSD', timeframe: '1h', overlays: [series()] });
    expect(csv).toContain('"Market","ETHUSD"');
    expect(csv).toContain('"Timeframe","1h"');
    expect(csv).toContain('"SMA(20) status","ok"');
    expect(csv).toContain('"Timestamp","SMA(20)"');
    expect(csv).toContain('100');
    expect(csv).toContain('101');
  });

  it('reports a failed overlay in metadata without a data column', () => {
    const csv = buildOverlayCsv({
      symbol: 'ETHUSD',
      timeframe: '1h',
      overlays: [series({ ok: false, error: 'Insufficient data.', data: [] })],
    });
    expect(csv).toContain('"SMA(20) status","Insufficient data."');
    const header = csv.split('\n').find((line) => line.startsWith('"Timestamp"'));
    expect(header).toBe('"Timestamp"');
  });

  it('unions timestamps across overlays with different warmup lengths', () => {
    const shortWarmup = series({ id: 'a', label: 'SMA(5)' });
    const longWarmup = series({
      id: 'b',
      label: 'SMA(50)',
      data: [{ time: 1_735_693_200, value: 999 }] as never,
    });
    const csv = buildOverlayCsv({
      symbol: 'ETHUSD',
      timeframe: '1h',
      overlays: [shortWarmup, longWarmup],
    });
    const rows = csv.split('\n').filter((line) => line.includes('202'));
    expect(rows).toHaveLength(2); // both timestamps appear, even though only one overlay has both
  });
});

describe('buildOverlayJson', () => {
  it('serializes symbol, timeframe, and each overlay with its series', () => {
    const payload = JSON.parse(
      buildOverlayJson({ symbol: 'ETHUSD', timeframe: '1h', overlays: [series()] }),
    ) as { symbol: string; overlays: { label: string; series: unknown[] }[] };
    expect(payload.symbol).toBe('ETHUSD');
    expect(payload.overlays[0]!.label).toBe('SMA(20)');
    expect(payload.overlays[0]!.series).toHaveLength(2);
  });
});

describe('buildOverlayValuesText', () => {
  it('is tab-separated and newest first', () => {
    const text = buildOverlayValuesText({
      symbol: 'ETHUSD',
      timeframe: '1h',
      overlays: [series()],
    });
    const lines = text.split('\n');
    expect(lines[0]).toBe('Timestamp\tSMA(20)');
    // Newest first: the later timestamp's row comes before the earlier one.
    expect(lines[1]).toContain('101');
    expect(lines[2]).toContain('100');
  });
});
