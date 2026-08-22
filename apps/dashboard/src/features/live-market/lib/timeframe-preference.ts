/**
 * Timeframe resolution for the live view.
 *
 * A live dashboard wants the finest resolution the platform actually stores,
 * because a 1d bar barely moves while you watch it; the History page's
 * coarser default is the right choice there and the wrong one here.
 */
export const LIVE_TIMEFRAME_PREFERENCE = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'] as const;

export interface ResolveTimeframeInput {
  /** Explicit in-session choice, which always wins. */
  selected: string | null;
  /** From the URL (`?timeframe=`). */
  requested: string | null;
  /** From local storage. */
  remembered: string | null;
  /** Timeframes that actually have stored candles for the current symbol. */
  available: string[];
}

/**
 * Picks the timeframe to display, ignoring any candidate the current symbol
 * has no candles for — a remembered `4h` must not blank the chart on a
 * market that only stores `1m`.
 */
export function resolveTimeframe({
  selected,
  requested,
  remembered,
  available,
}: ResolveTimeframeInput): string | null {
  if (available.length === 0) {
    return null;
  }
  for (const candidate of [selected, requested, remembered]) {
    if (candidate && available.includes(candidate)) {
      return candidate;
    }
  }
  const preferred = LIVE_TIMEFRAME_PREFERENCE.find((entry) => available.includes(entry));
  return preferred ?? available[0]!;
}
