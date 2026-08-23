import { describe, expect, it } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { METRIC_SAMPLE_INTERVAL_MS } from '../lib/metric-history';
import { TradeAnalyticsEngine } from './trade-analytics-engine';

function trade(price: string, size: string, eventTime: string, side = 'buy'): LiveTradeData {
  return { price, size, side, event_time: eventTime };
}

const T0 = Date.parse('2026-01-01T00:00:00Z');

describe('TradeAnalyticsEngine', () => {
  it('reports empty/null stats before any trade is ingested', () => {
    const engine = new TradeAnalyticsEngine();
    const snapshot = engine.snapshot(T0);
    expect(snapshot.sessionStats.tradeCount).toBe(0);
    expect(snapshot.vwap.session).toBeNull();
    expect(snapshot.rolling.tradesPerMinute).toBe(0);
    expect(snapshot.sentiment.label).toBe('neutral');
  });

  it('folds a trade into both session stats and the rolling window', () => {
    const engine = new TradeAnalyticsEngine();
    engine.ingest(trade('100', '2', new Date(T0).toISOString(), 'buy'));
    const snapshot = engine.snapshot(T0);
    expect(snapshot.sessionStats.tradeCount).toBe(1);
    expect(snapshot.sessionStats.buyVolume).toBe(2);
    expect(snapshot.rolling.tradesPerMinute).toBe(1);
    expect(snapshot.vwap.session).toBe(100);
  });

  it('silently drops an unparseable trade payload without throwing', () => {
    const engine = new TradeAnalyticsEngine();
    expect(() =>
      engine.ingest({
        price: 'not-a-number',
        size: '1',
        side: 'buy',
        event_time: new Date(T0).toISOString(),
      }),
    ).not.toThrow();
    expect(engine.snapshot(T0).sessionStats.tradeCount).toBe(0);
  });

  it('derives sentiment from the rolling buy/sell imbalance', () => {
    const engine = new TradeAnalyticsEngine();
    for (let i = 0; i < 5; i += 1) {
      engine.ingest(trade('100', '1', new Date(T0 + i).toISOString(), 'buy'));
    }
    expect(engine.snapshot(T0 + 10).sentiment.label).toBe('strongly-bullish');
  });

  it('reset() clears session, rolling window, and sample history together', () => {
    const engine = new TradeAnalyticsEngine();
    engine.ingest(trade('100', '1', new Date(T0).toISOString()));
    engine.snapshot(T0);
    engine.reset();
    // A snapshot right after reset takes one fresh sample (lastSampleAtMs is
    // cleared too), but nothing from before the reset survives into it.
    const snapshot = engine.snapshot(T0 + 1);
    expect(snapshot.sessionStats.tradeCount).toBe(0);
    expect(snapshot.history.timestamps).toEqual([T0 + 1]);
    expect(snapshot.history.buyVolume).toEqual([0]);
  });

  it('records at most one sparkline sample per METRIC_SAMPLE_INTERVAL_MS, regardless of trade frequency', () => {
    const engine = new TradeAnalyticsEngine();
    // Ten trades and ten snapshot() calls, all within one sample interval.
    for (let i = 0; i < 10; i += 1) {
      engine.ingest(trade('100', '1', new Date(T0 + i).toISOString()));
      engine.snapshot(T0 + i);
    }
    expect(engine.snapshot(T0 + 9).history.timestamps).toHaveLength(1);
  });

  it('records a new sparkline sample once the interval elapses', () => {
    const engine = new TradeAnalyticsEngine();
    engine.snapshot(T0);
    engine.snapshot(T0 + METRIC_SAMPLE_INTERVAL_MS);
    expect(engine.snapshot(T0 + METRIC_SAMPLE_INTERVAL_MS).history.timestamps).toHaveLength(2);
  });

  it('reports current price, session high/low, and VWAP distance together', () => {
    const engine = new TradeAnalyticsEngine();
    engine.ingest(trade('100', '1', new Date(T0).toISOString()));
    engine.ingest(trade('120', '1', new Date(T0 + 1).toISOString()));
    engine.ingest(trade('110', '1', new Date(T0 + 2).toISOString()));

    const snapshot = engine.snapshot(T0 + 3);
    expect(snapshot.sessionStats.lastPrice).toBe(110);
    expect(snapshot.sessionStats.sessionHigh).toBe(120);
    expect(snapshot.sessionStats.sessionLow).toBe(100);
    // Session VWAP is (100 + 120 + 110) / 3 = 110, so price sits exactly on it.
    expect(snapshot.vwapDistance?.absolute).toBeCloseTo(0);
    expect(snapshot.vwapDistance?.fraction).toBeCloseTo(0);
  });

  it('reports a null VWAP distance before any trade has printed', () => {
    expect(new TradeAnalyticsEngine().snapshot(T0).vwapDistance).toBeNull();
  });

  it('buckets recent trade sizes into a distribution over the trailing minute', () => {
    const engine = new TradeAnalyticsEngine();
    for (let i = 0; i < 9; i += 1) {
      engine.ingest(trade('100', '1', new Date(T0 + i).toISOString()));
    }
    engine.ingest(trade('100', '100', new Date(T0 + 9).toISOString()));

    const distribution = engine.snapshot(T0 + 10).sizeDistribution;
    expect(distribution.total).toBe(10);
    expect(distribution.buckets.at(-1)?.count).toBe(1); // the outsized print
  });

  it('never lets a trade older than 15 minutes leak into the 15m VWAP, however long the engine has run', () => {
    const engine = new TradeAnalyticsEngine();
    engine.ingest(trade('999', '1', new Date(T0).toISOString()));
    const muchLater = T0 + 20 * 60_000;
    engine.ingest(trade('100', '1', new Date(muchLater).toISOString()));
    expect(engine.snapshot(muchLater).vwap.fifteenMinute).toBe(100);
  });
});
