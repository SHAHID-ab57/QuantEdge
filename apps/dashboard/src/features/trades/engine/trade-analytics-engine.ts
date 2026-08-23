import type { LiveTradeData } from '@/types/api/market-stream';
import {
  deriveMetricHistory,
  METRIC_HISTORY_CAPACITY,
  METRIC_SAMPLE_INTERVAL_MS,
  type MetricHistory,
  type MetricSample,
} from '../lib/metric-history';
import { RingBuffer } from '../lib/ring-buffer';
import {
  computeRollingAnalytics,
  computeVwapSet,
  type RollingAnalytics,
  type VwapSet,
} from '../lib/rolling-window';
import { deriveSentiment, type MarketSentiment } from '../lib/sentiment';
import {
  createSessionAccumulator,
  deriveSessionStats,
  foldTradeIntoSession,
  type SessionAccumulator,
  type SessionStats,
} from '../lib/session-stats';
import { computeSizeDistribution, type SizeDistribution } from '../lib/size-distribution';
import { toTradeRecord, type TradeRecord } from '../lib/trade-record';
import { computeVwapDistance, type VwapDistance } from '../lib/vwap-distance';

/**
 * Sized so a real market can never fill 15 minutes of retention faster than
 * this buffer wraps: ~22 trades/second sustained for the full window. The
 * busiest bursts observed against the real gateway during this platform's
 * development were nowhere close to that; this is a documented ceiling, not
 * a tuned-to-the-edge number — see "Known scalability limits" in
 * `FRONTEND.md`.
 */
const ROLLING_WINDOW_CAPACITY = 20_000;

export interface TradeAnalyticsSnapshot {
  sessionStats: SessionStats;
  vwap: VwapSet;
  rolling: RollingAnalytics;
  sentiment: MarketSentiment;
  history: MetricHistory;
  /** Last traded price relative to session VWAP, or `null` before either exists. */
  vwapDistance: VwapDistance | null;
  /** Histogram of trade sizes over the trailing minute, bucketed relative to that window's average. */
  sizeDistribution: SizeDistribution;
}

/**
 * Owns every stateful accumulator behind the Live Trade Analytics
 * dashboard — the session totals, the rolling trade-level window, and the
 * sparkline sample history — behind exactly two operations: `ingest` (fold
 * one trade in) and `snapshot` (compute everything derived from the
 * current state, as of `nowMs`). Nothing here imports React or touches a
 * hook; `useTradeAnalytics` is a thin adapter that owns one instance in a
 * ref and calls these two methods, so a component only ever consumes an
 * already-computed `TradeAnalyticsSnapshot` and never a raw accumulator or
 * a bare calculation function. Framework-agnostic on purpose: this class is
 * unit-tested directly (`trade-analytics-engine.test.ts`) with no React
 * testing machinery involved, and could run outside a component unchanged.
 */
export class TradeAnalyticsEngine {
  private session: SessionAccumulator = createSessionAccumulator();
  private readonly window = new RingBuffer<TradeRecord>(ROLLING_WINDOW_CAPACITY);
  private readonly history = new RingBuffer<MetricSample>(METRIC_HISTORY_CAPACITY);
  private lastSampleAtMs: number | null = null;

  /** Folds one trade in. Silently drops an unparseable payload — see `toTradeRecord`. */
  ingest(trade: LiveTradeData): void {
    const record = toTradeRecord(trade);
    if (!record) {
      return;
    }
    this.session = foldTradeIntoSession(this.session, record);
    this.window.push(record);
  }

  /** Clears every accumulator — used when the tracked symbol changes. */
  reset(): void {
    this.session = createSessionAccumulator();
    this.window.clear();
    this.history.clear();
    this.lastSampleAtMs = null;
  }

  /**
   * Computes the full derived snapshot as of `nowMs`. Also opportunistically
   * records one sparkline sample if at least `METRIC_SAMPLE_INTERVAL_MS` has
   * elapsed since the last one — piggybacking on the same recompute calls
   * the hook already makes (on every new trade, and on a 1-second wall
   * clock tick) rather than needing a second timer.
   */
  snapshot(nowMs: number): TradeAnalyticsSnapshot {
    const sessionStats = deriveSessionStats(this.session);
    const records = this.window.toArray();
    const vwap = computeVwapSet(records, nowMs, sessionStats.sessionVwap);
    const rolling = computeRollingAnalytics(records, nowMs);
    const sentiment = deriveSentiment(rolling.buySellImbalance);

    if (this.lastSampleAtMs === null || nowMs - this.lastSampleAtMs >= METRIC_SAMPLE_INTERVAL_MS) {
      this.history.push({
        timestampMs: nowMs,
        buyVolume: rolling.buyVolume,
        sellVolume: rolling.sellVolume,
        tradesPerMinute: rolling.tradesPerMinute,
        volumePerMinute: rolling.volumePerMinute,
        vwapOneMinute: vwap.oneMinute,
        avgTradeSize: rolling.avgTradeSize,
      });
      this.lastSampleAtMs = nowMs;
    }

    return {
      sessionStats,
      vwap,
      rolling,
      sentiment,
      history: deriveMetricHistory(this.history.toArray()),
      vwapDistance: computeVwapDistance(sessionStats.lastPrice, sessionStats.sessionVwap),
      sizeDistribution: computeSizeDistribution(records, nowMs),
    };
  }
}
