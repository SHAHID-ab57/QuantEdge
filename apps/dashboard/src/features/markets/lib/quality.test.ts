import { describe, expect, it } from 'vitest';
import {
  computeQualityScore,
  qualityBreakdown,
  qualityLabel,
  qualityRecommendations,
} from './quality';

const NOW = Date.parse('2026-08-20T16:33:35Z');

describe('computeQualityScore', () => {
  it('scores a perfect market 100/100 (Good)', () => {
    const score = computeQualityScore({
      timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'],
      totalCandles: 150_000,
      lastSyncAt: new Date(NOW - 30_000).toISOString(),
      now: NOW,
    });
    expect(score).toBe(100);
    expect(qualityLabel(score)).toBe('Good');
  });

  it('matches the ETHUSD regression: 49/100 (Poor)', () => {
    const score = computeQualityScore({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: '2026-08-19T17:00:00Z',
      now: NOW,
    });
    expect(score).toBe(49);
    expect(qualityLabel(score)).toBe('Poor');
  });

  it('scores a live-updating but thin market 59/100 (Fair)', () => {
    const score = computeQualityScore({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: new Date(NOW - 120_000).toISOString(),
      now: NOW,
    });
    expect(score).toBe(59);
    expect(qualityLabel(score)).toBe('Fair');
  });

  it('drops freshness to 40 between 1h and 24h', () => {
    const score = computeQualityScore({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: new Date(NOW - 2 * 3_600_000).toISOString(),
      now: NOW,
    });
    expect(score).toBe(49);
  });

  it('drops freshness to 25 after 24 hours', () => {
    const score = computeQualityScore({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: new Date(NOW - 25 * 3_600_000).toISOString(),
      now: NOW,
    });
    expect(score).toBe(34);
  });

  it('drops freshness to 10 after 7 days', () => {
    const score = computeQualityScore({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: new Date(NOW - 8 * 86_400_000).toISOString(),
      now: NOW,
    });
    expect(score).toBe(19);
  });

  it('drops freshness to 0 after 30 days', () => {
    const score = computeQualityScore({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: new Date(NOW - 31 * 86_400_000).toISOString(),
      now: NOW,
    });
    expect(score).toBe(9);
  });

  it('scores an empty market 0/100 (Poor)', () => {
    const score = computeQualityScore({
      timeframes: [],
      totalCandles: 0,
      lastSyncAt: null,
      now: NOW,
    });
    expect(score).toBe(0);
    expect(qualityLabel(score)).toBe('Poor');
  });

  it('scores partial timeframe coverage proportionally', () => {
    const base = {
      totalCandles: 150_000,
      lastSyncAt: new Date(NOW - 30_000).toISOString(),
      now: NOW,
    };
    expect(computeQualityScore({ ...base, timeframes: ['1m', '5m', '15m', '30m'] })).toBe(85);
    expect(
      computeQualityScore({ ...base, timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d'] }),
    ).toBe(96);
  });

  it('scores volume tiers correctly', () => {
    const base = {
      timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'],
      lastSyncAt: new Date(NOW - 30_000).toISOString(),
      now: NOW,
    };
    expect(computeQualityScore({ ...base, totalCandles: 100_000 })).toBe(100);
    expect(computeQualityScore({ ...base, totalCandles: 10_000 })).toBe(95);
    expect(computeQualityScore({ ...base, totalCandles: 1_000 })).toBe(90);
    expect(computeQualityScore({ ...base, totalCandles: 100 })).toBe(85);
    expect(computeQualityScore({ ...base, totalCandles: 0 })).toBe(80);
  });

  it('labels boundaries at 80 and 50', () => {
    expect(qualityLabel(80)).toBe('Good');
    expect(qualityLabel(79)).toBe('Fair');
    expect(qualityLabel(50)).toBe('Fair');
    expect(qualityLabel(49)).toBe('Poor');
  });
});

describe('qualityBreakdown', () => {
  it('explains the ETHUSD 49 score factor by factor', () => {
    const rows = qualityBreakdown({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: '2026-08-19T17:00:00Z',
      now: NOW,
    });
    expect(rows).toHaveLength(3);
    expect(rows[0]).toMatchObject({
      id: 'freshness',
      points: 40,
      max: 50,
      status: 'warn',
      detail: 'Latest candle is within the last 24 hours',
    });
    expect(rows[1]).toMatchObject({
      id: 'coverage',
      points: 4,
      max: 30,
      status: 'warn',
      detail: '1 of 8 standard timeframes synced',
    });
    expect(rows[2]).toMatchObject({
      id: 'volume',
      points: 5,
      max: 20,
      status: 'warn',
      detail: 'More than 100 candles stored',
    });
    expect(rows.reduce((sum, row) => sum + row.points, 0)).toBe(49);
  });

  it('marks all factors pass for a perfect market', () => {
    const rows = qualityBreakdown({
      timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'],
      totalCandles: 150_000,
      lastSyncAt: new Date(NOW - 30_000).toISOString(),
      now: NOW,
    });
    expect(rows.every((row) => row.status === 'pass')).toBe(true);
    expect(rows.reduce((sum, row) => sum + row.points, 0)).toBe(100);
  });

  it('marks an empty market with zero points and fail status', () => {
    const rows = qualityBreakdown({ timeframes: [], totalCandles: 0, lastSyncAt: null, now: NOW });
    expect(rows).toHaveLength(3);
    expect(rows.every((row) => row.points === 0 && row.status === 'fail')).toBe(true);
  });

  it('marks a stale market as fail on freshness', () => {
    const rows = qualityBreakdown({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: new Date(NOW - 8 * 86_400_000).toISOString(),
      now: NOW,
    });
    expect(rows.find((row) => row.id === 'freshness')).toMatchObject({
      points: 10,
      status: 'fail',
      detail: 'Latest candle is more than a week old',
    });
  });
});

describe('qualityRecommendations', () => {
  it('recommends the missing timeframes for ETHUSD', () => {
    const recommendations = qualityRecommendations({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: '2026-08-19T17:00:00Z',
      now: NOW,
    });
    expect(recommendations).toContain('Enable additional timeframes: 1m, 5m, 15m, 30m, 4h, 1d, 1w');
    expect(recommendations).toContain(
      'Latest candle is 23h old — ensure the candle sync scheduler is running',
    );
    expect(recommendations).toContain('Synchronize additional historical candles (backfill)');
  });

  it('asks for the first data set on an empty market', () => {
    const recommendations = qualityRecommendations({
      timeframes: [],
      totalCandles: 0,
      lastSyncAt: null,
      now: NOW,
    });
    expect(recommendations).toContain(
      'Synchronize historical candles to create the first data set',
    );
  });

  it('reports current and complete when everything is healthy', () => {
    const recommendations = qualityRecommendations({
      timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'],
      totalCandles: 150_000,
      lastSyncAt: new Date(NOW - 30_000).toISOString(),
      now: NOW,
    });
    expect(recommendations).toEqual(['Data is current and complete']);
  });

  it('reports no staleness recommendation for a fresh market', () => {
    const recommendations = qualityRecommendations({
      timeframes: ['1h'],
      totalCandles: 137,
      lastSyncAt: new Date(NOW - 120_000).toISOString(),
      now: NOW,
    });
    expect(recommendations.some((item) => item.includes('ensure the candle sync scheduler'))).toBe(
      false,
    );
    expect(recommendations).toContain('Enable additional timeframes: 1m, 5m, 15m, 30m, 4h, 1d, 1w');
  });
});
