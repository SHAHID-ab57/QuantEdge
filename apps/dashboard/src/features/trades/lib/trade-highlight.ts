/**
 * How many multiples of the session's average trade notional value counts
 * as "unusually large" for the trade tape's highlight — a fixed, documented
 * rule (not a statistical outlier test) so the highlight behaves
 * predictably rather than shifting definition as more data arrives.
 */
export const LARGE_TRADE_MULTIPLIER = 5;

/**
 * `value` is one trade's notional (price × size); `avgTradeValue` is the
 * session average notional (`SessionStats.avgTradeValue`). Returns `false`
 * until there is a baseline to compare against (fewer than one trade seen,
 * or an average of zero).
 */
export function isLargeTrade(value: number, avgTradeValue: number | null): boolean {
  if (avgTradeValue === null || avgTradeValue <= 0) {
    return false;
  }
  return value >= avgTradeValue * LARGE_TRADE_MULTIPLIER;
}
