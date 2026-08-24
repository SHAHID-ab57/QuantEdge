/**
 * Formats a duration in milliseconds as a compact `"1h 15m"` /
 * `"2m 30s"` / `"45s"` string — used for elapsed/remaining replay-data
 * time on the timeline and for the status panel's estimated completion.
 * Deliberately not `Intl.DurationFormat` (limited runtime/polyfill support
 * at the time this was written) or a date library — a duration this
 * dashboard ever needs to show tops out in the tens of hours, so plain
 * arithmetic is simpler and dependency-free.
 */
export function formatDuration(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms) || ms < 0) {
    return '—';
  }
  const totalSeconds = Math.round(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

/**
 * Estimated wall-clock time remaining to finish replaying the currently
 * loaded session at `speed` — `remainingCandles * tickIntervalMs(speed)`,
 * i.e. actual playback pacing (see `replay-speed.ts`'s `BASE_TICK_MS`
 * doc), not the span of market time the remaining candles cover. `null`
 * while nothing is loaded or already at the end.
 */
export function estimateCompletionMs(
  remainingCandles: number,
  tickIntervalMs: number,
): number | null {
  if (remainingCandles <= 0) {
    return 0;
  }
  return remainingCandles * tickIntervalMs;
}
