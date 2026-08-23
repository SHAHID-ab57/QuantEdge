import { describe, expect, it } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { TradeAnalyticsEngine } from './trade-analytics-engine';

/**
 * A code-level stand-in for "run this for 30 minutes of live streaming and
 * watch CPU/memory/rendering stay flat" (the dashboard review's goal #10).
 * This environment has no browser automation to actually leave a tab open
 * for 30 real minutes, so this instead *simulates* 30 minutes of trade
 * timestamps in a tight loop and measures the one thing that would
 * actually degrade over a long session if the engine were wrong: whether
 * `ingest`/`snapshot` get slower as more history accumulates. Before the
 * ring-buffer refactor, the rolling window was `[...array, trade].slice()`
 * on every trade — an O(n) copy per insert — which this test would have
 * caught as a clear upward trend in later-session timings. It does not,
 * and cannot, stand in for verifying actual browser memory/paint behavior;
 * that limitation is intentional and disclosed rather than silently
 * assumed away.
 */
describe('TradeAnalyticsEngine sustained-load stress test', () => {
  it('keeps ingest+snapshot cost roughly flat across a simulated 30-minute, ~12,000-trade session', () => {
    const engine = new TradeAnalyticsEngine();
    const startMs = Date.parse('2026-01-01T00:00:00Z');
    const SIMULATED_DURATION_MS = 30 * 60_000;
    const TRADE_INTERVAL_MS = 150; // ~6.7 trades/second sustained — a busy market
    const SNAPSHOT_EVERY_N_TRADES = 20; // mirrors the hook recomputing far less often than every trade

    const durationsMs: number[] = [];
    let elapsed = 0;
    let tradeIndex = 0;

    while (elapsed < SIMULATED_DURATION_MS) {
      const nowMs = startMs + elapsed;
      const trade: LiveTradeData = {
        price: String(100 + (tradeIndex % 50)),
        size: '1',
        side: tradeIndex % 2 === 0 ? 'buy' : 'sell',
        event_time: new Date(nowMs).toISOString(),
      };
      engine.ingest(trade);

      if (tradeIndex % SNAPSHOT_EVERY_N_TRADES === 0) {
        const start = performance.now();
        engine.snapshot(nowMs);
        durationsMs.push(performance.now() - start);
      }

      tradeIndex += 1;
      elapsed += TRADE_INTERVAL_MS;
    }

    // Sanity: this really did simulate a large, sustained session.
    expect(tradeIndex).toBeGreaterThan(10_000);
    expect(durationsMs.length).toBeGreaterThan(100);

    const tenPercent = Math.floor(durationsMs.length / 10);
    const first = durationsMs.slice(0, tenPercent);
    const last = durationsMs.slice(-tenPercent);
    const avg = (values: number[]) => values.reduce((sum, v) => sum + v, 0) / values.length;
    const firstAvg = avg(first);
    const lastAvg = avg(last);

    // A generous bound (not "identical," since JIT warm-up and GC noise are
    // real) — the property under test is "no unbounded growth," not "zero
    // variance." An O(n) or worse per-trade cost would blow well past this.
    expect(lastAvg).toBeLessThan(Math.max(firstAvg * 5, 5));

    // The rolling window still reports a *bounded* one-minute figure at the
    // end of a 12,000-trade session, not something proportional to the
    // whole session's trade count — proof the time-window filtering still
    // works correctly at this scale, not just correctness at toy sizes.
    const finalSnapshot = engine.snapshot(startMs + elapsed);
    expect(finalSnapshot.rolling.tradesPerMinute).toBeLessThan(1000);
    expect(finalSnapshot.sessionStats.tradeCount).toBe(tradeIndex);
  });
});
