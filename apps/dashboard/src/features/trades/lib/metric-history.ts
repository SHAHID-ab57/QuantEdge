/**
 * Periodic samples of the rolling-window metrics, kept for the dashboard's
 * sparklines (Buy vs Sell Volume, Trades/Minute, Volume/Minute, Rolling
 * VWAP, Average Trade Size). This is a *separate* history from the
 * trade-level rolling window in `rolling-window.ts` — that buffer holds raw
 * trades for computing a figure *right now*; this one holds a trail of
 * already-computed figures *over time*, at a fixed sampling cadence, so a
 * sparkline shows a trend instead of a single point.
 */
export interface MetricSample {
  timestampMs: number;
  /** Buy/sell volume within the trailing one-minute window at sample time. */
  buyVolume: number;
  sellVolume: number;
  tradesPerMinute: number;
  volumePerMinute: number;
  vwapOneMinute: number | null;
  avgTradeSize: number | null;
}

/** How often a new sample is taken, regardless of how often trades arrive. */
export const METRIC_SAMPLE_INTERVAL_MS = 2_000;

/** How many samples are retained — at the interval above, ~5 minutes of trend. */
export const METRIC_HISTORY_CAPACITY = 150;

/** One flattened array per metric — the shape sparkline components consume directly. */
export interface MetricHistory {
  timestamps: number[];
  buyVolume: number[];
  sellVolume: number[];
  tradesPerMinute: number[];
  volumePerMinute: number[];
  vwapOneMinute: (number | null)[];
  avgTradeSize: (number | null)[];
}

/** `samples` must already be oldest-to-newest (a `RingBuffer<MetricSample>`'s natural iteration order). */
export function deriveMetricHistory(samples: readonly MetricSample[]): MetricHistory {
  return {
    timestamps: samples.map((s) => s.timestampMs),
    buyVolume: samples.map((s) => s.buyVolume),
    sellVolume: samples.map((s) => s.sellVolume),
    tradesPerMinute: samples.map((s) => s.tradesPerMinute),
    volumePerMinute: samples.map((s) => s.volumePerMinute),
    vwapOneMinute: samples.map((s) => s.vwapOneMinute),
    avgTradeSize: samples.map((s) => s.avgTradeSize),
  };
}
