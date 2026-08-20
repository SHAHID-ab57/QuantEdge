export const TIMEFRAME_ORDER = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'];

export function sortTimeframes(timeframes: string[]): string[] {
  const known = new Map(TIMEFRAME_ORDER.map((timeframe, index) => [timeframe, index]));
  return [...timeframes].sort((left, right) => {
    const leftIndex = known.get(left);
    const rightIndex = known.get(right);
    if (leftIndex !== undefined && rightIndex !== undefined) {
      return leftIndex - rightIndex;
    }
    if (leftIndex !== undefined) {
      return -1;
    }
    if (rightIndex !== undefined) {
      return 1;
    }
    return left.localeCompare(right);
  });
}
