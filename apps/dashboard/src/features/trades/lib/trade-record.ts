import type { LiveTradeData } from '@/types/api/market-stream';

/**
 * The internal shape every analytics calculation in this feature operates
 * on — parsed once from the wire's string fields into numbers, plus the
 * derived `value` (notional = price × size) that VWAP, "largest trade,"
 * and the trade tape's Trade Value column all need repeatedly.
 */
export interface TradeRecord {
  price: number;
  size: number;
  /** price × size — the trade's notional value. */
  value: number;
  side: 'buy' | 'sell' | 'unknown';
  /** Exchange event time, epoch milliseconds. */
  timestampMs: number;
}

/**
 * Converts a wire trade into a `TradeRecord`, or `null` if any field is
 * unparseable — mirroring `toLiveCandlePoint`'s convention elsewhere in
 * this codebase: a bad input degrades to "nothing to fold in," never a
 * `NaN` that would corrupt every downstream sum.
 */
export function toTradeRecord(trade: LiveTradeData): TradeRecord | null {
  const price = Number(trade.price);
  const size = Number(trade.size);
  const timestampMs = Date.parse(trade.event_time);
  if (!Number.isFinite(price) || !Number.isFinite(size) || !Number.isFinite(timestampMs)) {
    return null;
  }
  const side = trade.side === 'buy' || trade.side === 'sell' ? trade.side : 'unknown';
  return { price, size, value: price * size, side, timestampMs };
}
