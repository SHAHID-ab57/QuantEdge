import { describe, expect, it } from 'vitest';
import type { IndicatorCalculation } from '@/types/api/indicators';
import { buildApiRequestUrl, buildCsv, buildJson, buildValuesText, exportFileName } from './export';

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
    parameters: { period: 2, source: 'close' },
    timestamps: ['2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z'],
    series: [{ name: 'sma', label: 'SMA(2)', values: [null, 17.5] }],
    meta: {
      candles_analyzed: 2,
      warmup_candles: 1,
      execution_time_ms: 0.1,
      database_time_ms: 1,
      cache_status: 'miss',
      generated_at: '2026-01-01T02:00:00Z',
    },
    ...overrides,
  };
}

describe('exportFileName', () => {
  it('composes symbol, indicator, and timeframe', () => {
    expect(exportFileName(result(), 'csv')).toBe('ETHUSD-sma-1h.csv');
  });

  it('sanitizes unsafe characters', () => {
    expect(exportFileName(result({ symbol: 'ETH/USD' }), 'json')).toBe('ETH-USD-sma-1h.json');
  });
});

describe('buildCsv', () => {
  it('includes a metadata block naming the market, indicator, and parameters', () => {
    const csv = buildCsv(result());
    expect(csv).toContain('"Market","ETHUSD"');
    expect(csv).toContain('"Indicator","Simple Moving Average"');
    expect(csv).toContain('""period"":2');
  });

  it('renders one data row per candle in chronological order', () => {
    const csv = buildCsv(result());
    const lines = csv.split('\n');
    const firstDataRow = lines.find((line) => line.startsWith('"2026-01-01T00'));
    const secondDataRow = lines.find((line) => line.startsWith('"2026-01-01T01'));
    expect(lines.indexOf(firstDataRow!)).toBeLessThan(lines.indexOf(secondDataRow!));
  });

  it('renders a warmup null as an empty cell, not the literal word null', () => {
    const csv = buildCsv(result());
    expect(csv).toContain('"2026-01-01T00:00:00Z",""');
  });
});

describe('buildJson', () => {
  it('round-trips the full result', () => {
    const parsed = JSON.parse(buildJson(result())) as IndicatorCalculation;
    expect(parsed.symbol).toBe('ETHUSD');
    expect(parsed.series[0]?.values).toEqual([null, 17.5]);
  });
});

describe('buildValuesText', () => {
  it('is tab-separated', () => {
    const text = buildValuesText(result());
    expect(text.split('\n')[0]).toBe('Timestamp\tSMA(2)');
  });

  it('lists rows newest first, matching the results table', () => {
    const text = buildValuesText(result());
    const rows = text.split('\n').slice(1);
    expect(rows[0]).toContain('2026-01-01T01:00:00Z');
    expect(rows[1]).toContain('2026-01-01T00:00:00Z');
  });
});

describe('buildApiRequestUrl', () => {
  it('assembles the same path shape the API client uses', () => {
    const url = buildApiRequestUrl('http://localhost:8000', 'ETHUSD', 'sma', '1h', {
      period: '20',
    });
    expect(url).toBe(
      'http://localhost:8000/api/v1/markets/ETHUSD/indicators/sma?timeframe=1h&period=20',
    );
  });

  it('strips a trailing slash from the base URL', () => {
    const url = buildApiRequestUrl('http://localhost:8000/', 'ETHUSD', 'sma', '1h', {});
    expect(url.startsWith('http://localhost:8000/api/v1')).toBe(true);
  });

  it('url-encodes the symbol and indicator name', () => {
    const url = buildApiRequestUrl('http://localhost:8000', 'ETH USD', 'my indicator', '1h', {});
    expect(url).toContain('/markets/ETH%20USD/indicators/my%20indicator');
  });
});
