import { describe, expect, it } from 'vitest';
import { getIndicatorKnowledge } from './indicator-knowledge';
import { summarizeSeries } from './result-analysis';
import type { Indicator, IndicatorSeries } from '@/types/api/indicators';

function series(values: (number | null)[], name = 'sma', label = 'SMA(3)'): IndicatorSeries {
  return { name, label, values };
}

function catalogueEntry(name: string, description = 'Stub.'): Indicator {
  return {
    name,
    label: name.toUpperCase(),
    description,
    category: 'trend',
    parameters: [],
    outputs: [],
  };
}

const sma = getIndicatorKnowledge(catalogueEntry('sma'));
const rsi = getIndicatorKnowledge(catalogueEntry('rsi'));

describe('summarizeSeries — latest/previous', () => {
  it('reports the latest and previous non-null values', () => {
    const summary = summarizeSeries(series([null, 10, 20, 30]), sma);
    expect(summary.latest).toBe(30);
    expect(summary.previous).toBe(20);
  });

  it('skips a trailing null, still finding a real latest value', () => {
    const summary = summarizeSeries(series([10, 20, null]), sma);
    expect(summary.latest).toBe(20);
    expect(summary.previous).toBe(10);
  });

  it('reports null for both when there are fewer than two real values', () => {
    const summary = summarizeSeries(series([null, null, 5]), sma);
    expect(summary.latest).toBe(5);
    expect(summary.previous).toBeNull();
  });

  it('reports null for everything when the series is entirely null', () => {
    const summary = summarizeSeries(series([null, null]), sma);
    expect(summary.latest).toBeNull();
    expect(summary.previous).toBeNull();
  });
});

describe('summarizeSeries — change', () => {
  it('computes the absolute change', () => {
    const summary = summarizeSeries(series([100, 110]), sma);
    expect(summary.absoluteChange).toBe(10);
  });

  it('computes the percent change relative to the previous value', () => {
    const summary = summarizeSeries(series([100, 110]), sma);
    expect(summary.percentChange).toBeCloseTo(10, 5);
  });

  it('handles a negative previous value using its magnitude as the base', () => {
    const summary = summarizeSeries(series([-100, -90]), sma);
    expect(summary.absoluteChange).toBe(10);
    expect(summary.percentChange).toBeCloseTo(10, 5);
  });

  it('reports null percent change rather than dividing by zero', () => {
    const summary = summarizeSeries(series([0, 5]), sma);
    expect(summary.absoluteChange).toBe(5);
    expect(summary.percentChange).toBeNull();
  });

  it('reports null change when there is no previous value', () => {
    const summary = summarizeSeries(series([null, 5]), sma);
    expect(summary.absoluteChange).toBeNull();
    expect(summary.percentChange).toBeNull();
  });
});

describe('summarizeSeries — trend', () => {
  it('reads up when the value rose', () => {
    expect(summarizeSeries(series([10, 20]), sma).trend).toBe('up');
  });

  it('reads down when the value fell', () => {
    expect(summarizeSeries(series([20, 10]), sma).trend).toBe('down');
  });

  it('reads flat when the value is unchanged', () => {
    expect(summarizeSeries(series([10, 10]), sma).trend).toBe('flat');
  });

  it('is null without a previous value to compare against', () => {
    expect(summarizeSeries(series([10]), sma).trend).toBeNull();
  });
});

describe('summarizeSeries — signal, generic fallback', () => {
  it('falls back to trend direction for an indicator with no classifySignal', () => {
    expect(summarizeSeries(series([10, 20]), sma).signal).toBe('bullish');
    expect(summarizeSeries(series([20, 10]), sma).signal).toBe('bearish');
    expect(summarizeSeries(series([10, 10]), sma).signal).toBe('neutral');
  });

  it('is null when trend itself cannot be computed', () => {
    expect(summarizeSeries(series([10]), sma).signal).toBeNull();
  });
});

describe('summarizeSeries — signal, indicator-specific thresholds', () => {
  it('reads an RSI above 70 as bearish (overbought) regardless of trend direction', () => {
    // Still rising into overbought territory — the threshold, not the
    // direction, should win for an indicator with its own convention.
    const summary = summarizeSeries(series([60, 75], 'rsi', 'RSI(14)'), rsi);
    expect(summary.trend).toBe('up');
    expect(summary.signal).toBe('bearish');
  });

  it('reads an RSI below 30 as bullish (oversold)', () => {
    const summary = summarizeSeries(series([40, 25], 'rsi', 'RSI(14)'), rsi);
    expect(summary.signal).toBe('bullish');
  });

  it('reads an RSI between 30 and 70 as neutral', () => {
    const summary = summarizeSeries(series([45, 55], 'rsi', 'RSI(14)'), rsi);
    expect(summary.signal).toBe('neutral');
  });

  it('is null when there is no latest value to classify', () => {
    expect(summarizeSeries(series([null, null], 'rsi', 'RSI(14)'), rsi).signal).toBeNull();
  });
});
