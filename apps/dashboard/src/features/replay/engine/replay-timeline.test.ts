import { describe, expect, it } from 'vitest';
import type { Candle } from '@/types/api/market';
import {
  clampIndex,
  computeTimeline,
  indexForProgress,
  indexForTimestamp,
} from './replay-timeline';

function candle(openTimeIso: string): Candle {
  return {
    open_time: openTimeIso,
    close_time: openTimeIso,
    open: '1',
    high: '1',
    low: '1',
    close: '1',
    volume: '1',
    source: 'test',
  };
}

const candles = [
  candle('2026-01-01T00:00:00Z'),
  candle('2026-01-01T00:01:00Z'),
  candle('2026-01-01T00:02:00Z'),
  candle('2026-01-01T00:03:00Z'),
  candle('2026-01-01T00:04:00Z'),
];

describe('clampIndex', () => {
  it('clamps to the valid range', () => {
    expect(clampIndex(-5, 5)).toBe(0);
    expect(clampIndex(100, 5)).toBe(4);
    expect(clampIndex(2, 5)).toBe(2);
  });

  it('returns 0 for an empty collection regardless of index', () => {
    expect(clampIndex(3, 0)).toBe(0);
  });
});

describe('computeTimeline', () => {
  it('reports nulls and zero progress with no candles loaded', () => {
    const timeline = computeTimeline([], 0);
    expect(timeline).toEqual({
      startMs: null,
      endMs: null,
      currentMs: null,
      progress: 0,
      totalCandles: 0,
      position: 0,
    });
  });

  it('reports start/end/current and a 1-based position', () => {
    const timeline = computeTimeline(candles, 2);
    expect(timeline.startMs).toBe(Date.parse('2026-01-01T00:00:00Z'));
    expect(timeline.endMs).toBe(Date.parse('2026-01-01T00:04:00Z'));
    expect(timeline.currentMs).toBe(Date.parse('2026-01-01T00:02:00Z'));
    expect(timeline.position).toBe(3);
    expect(timeline.totalCandles).toBe(5);
  });

  it('reports 0% progress at the first candle and 100% at the last', () => {
    expect(computeTimeline(candles, 0).progress).toBe(0);
    expect(computeTimeline(candles, 4).progress).toBe(100);
  });

  it('reports 50% progress at the midpoint of an evenly-spaced range', () => {
    expect(computeTimeline(candles, 2).progress).toBeCloseTo(50);
  });

  it('clamps an out-of-range index rather than throwing', () => {
    expect(computeTimeline(candles, 999).position).toBe(5);
    expect(computeTimeline(candles, -1).position).toBe(1);
  });

  it('reports 100% progress for a single-candle session', () => {
    expect(computeTimeline([candle('2026-01-01T00:00:00Z')], 0).progress).toBe(100);
  });
});

describe('indexForTimestamp', () => {
  it('finds the exact candle at a matching timestamp', () => {
    expect(indexForTimestamp(candles, Date.parse('2026-01-01T00:02:00Z'))).toBe(2);
  });

  it('finds the candle at or before a timestamp that falls between two candles', () => {
    expect(indexForTimestamp(candles, Date.parse('2026-01-01T00:02:30Z'))).toBe(2);
  });

  it('clamps to the first candle for a timestamp before the range', () => {
    expect(indexForTimestamp(candles, Date.parse('2025-01-01T00:00:00Z'))).toBe(0);
  });

  it('clamps to the last candle for a timestamp after the range', () => {
    expect(indexForTimestamp(candles, Date.parse('2027-01-01T00:00:00Z'))).toBe(4);
  });

  it('returns 0 for an empty candle list', () => {
    expect(indexForTimestamp([], Date.now())).toBe(0);
  });
});

describe('indexForProgress', () => {
  it('maps 0% and 100% to the first and last candle', () => {
    expect(indexForProgress(candles, 0)).toBe(0);
    expect(indexForProgress(candles, 100)).toBe(4);
  });

  it('maps 50% to the midpoint', () => {
    expect(indexForProgress(candles, 50)).toBe(2);
  });

  it('clamps an out-of-range percentage', () => {
    expect(indexForProgress(candles, -10)).toBe(0);
    expect(indexForProgress(candles, 250)).toBe(4);
  });

  it('round-trips with computeTimeline’s progress for every candle', () => {
    for (let i = 0; i < candles.length; i += 1) {
      const progress = computeTimeline(candles, i).progress;
      expect(indexForProgress(candles, progress)).toBe(i);
    }
  });
});
