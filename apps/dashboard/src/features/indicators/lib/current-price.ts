import type { Candle } from '@/types/api/market';

const PRICE_FIELDS = ['open', 'high', 'low', 'close'] as const;
type PriceField = (typeof PRICE_FIELDS)[number];

/**
 * Reads the field of a candle matching an indicator's resolved `source`
 * parameter, so "Current Price" compares against the same price series
 * the indicator itself was calculated on — comparing a high-based WMA
 * against the candle's close would be a subtly misleading mismatch.
 * Falls back to `close` for an indicator with no `source` parameter at
 * all (e.g. a future volume-based indicator).
 */
export function extractCurrentPrice(candle: Candle, source: unknown): number {
  const field: PriceField = isPriceField(source) ? source : 'close';
  return Number(candle[field]);
}

function isPriceField(value: unknown): value is PriceField {
  return typeof value === 'string' && (PRICE_FIELDS as readonly string[]).includes(value);
}
