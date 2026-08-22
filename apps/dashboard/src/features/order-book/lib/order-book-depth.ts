import type { OrderBookLevelData } from '@/types/api/market-stream';

/**
 * Pure order-book math: cumulative depth, spread, and mid-price. The
 * gateway already sorts and depth-caps (`app/marketdata/gateway.py`'s
 * `_ORDERBOOK_DEPTH`, 100), so everything here only ever slices further
 * (to the user's chosen depth) and derives numbers from what it's given —
 * no re-sorting, no network, fully testable without a render or a socket.
 */

export const DEPTH_OPTIONS = [10, 25, 50, 100] as const;
export type DepthOption = (typeof DEPTH_OPTIONS)[number];
export const DEFAULT_DEPTH: DepthOption = 25;

export interface DepthRow {
  price: number;
  size: number;
  /** Running total of `size` from the best price outward (inclusive). */
  total: number;
  /** `total` as a fraction of the deepest row's `total` in this slice — for the depth bar. */
  depthRatio: number;
}

function toNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Slices `levels` to `depth` (best price first — the caller must already
 * have them sorted: bids descending, asks ascending) and computes a
 * running cumulative size plus a 0–1 ratio against the deepest row in the
 * slice, which is exactly what a depth-visualization bar's width needs.
 * An empty or unparseable input yields `[]`, never a row with `NaN` in it.
 */
export function computeDepthRows(levels: OrderBookLevelData[], depth: number): DepthRow[] {
  const sliced = levels.slice(0, depth);
  let running = 0;
  const rows = sliced.map((level) => {
    const price = toNumber(level.price);
    const size = toNumber(level.size);
    running += size;
    return { price, size, total: running, depthRatio: 0 };
  });
  const maxTotal = rows.at(-1)?.total ?? 0;
  if (maxTotal <= 0) {
    return rows;
  }
  return rows.map((row) => ({ ...row, depthRatio: row.total / maxTotal }));
}

export interface SpreadSummary {
  bestBid: number | null;
  bestAsk: number | null;
  spread: number | null;
  /** Spread as a percentage of the mid price, or `null` when either side is missing. */
  spreadPercent: number | null;
  midPrice: number | null;
}

/**
 * Best bid/ask, spread, spread%, and mid price from the two best-priced
 * levels. Requires both sides to be non-empty — a one-sided book (e.g. one
 * side momentarily empty during a resync) reports every field as `null`
 * rather than a misleading zero spread.
 */
export function computeSpread(
  bids: OrderBookLevelData[],
  asks: OrderBookLevelData[],
): SpreadSummary {
  const bestBid = bids[0] ? toNumber(bids[0].price) : null;
  const bestAsk = asks[0] ? toNumber(asks[0].price) : null;
  if (bestBid === null || bestAsk === null) {
    return { bestBid, bestAsk, spread: null, spreadPercent: null, midPrice: null };
  }
  const spread = bestAsk - bestBid;
  const midPrice = (bestBid + bestAsk) / 2;
  const spreadPercent = midPrice > 0 ? (spread / midPrice) * 100 : null;
  return { bestBid, bestAsk, spread, spreadPercent, midPrice };
}
