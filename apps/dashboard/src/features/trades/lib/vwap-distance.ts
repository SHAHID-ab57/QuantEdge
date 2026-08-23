/**
 * How far the last traded price sits from a reference VWAP — the standard
 * "am I buying above or below the session's average execution price?"
 * check. Positive means the market is trading _above_ VWAP.
 */
export interface VwapDistance {
  /** `lastPrice - vwap`, in quote currency. */
  absolute: number;
  /** `(lastPrice - vwap) / vwap`, as a fraction (0.01 = 1% above VWAP). */
  fraction: number;
}

/**
 * Returns `null` when either input is missing (no trade yet, or no VWAP to
 * compare against) or when VWAP is zero — dividing by it would produce an
 * `Infinity` this dashboard would then have to special-case downstream.
 */
export function computeVwapDistance(
  lastPrice: number | null,
  vwap: number | null,
): VwapDistance | null {
  if (lastPrice === null || vwap === null || vwap === 0) {
    return null;
  }
  const absolute = lastPrice - vwap;
  return { absolute, fraction: absolute / vwap };
}
