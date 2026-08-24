import type { Candle } from '@/types/api/market';

export interface ReplayTimeline {
  /** `open_time` of the first loaded candle, epoch ms. `null` with no candles loaded. */
  startMs: number | null;
  /** `open_time` of the last loaded candle, epoch ms. `null` with no candles loaded. */
  endMs: number | null;
  /** `open_time` of the candle at `currentIndex`, epoch ms. `null` with no candles loaded. */
  currentMs: number | null;
  /** How far through the loaded range `currentIndex` sits, in [0, 100]. `0` with no candles loaded. */
  progress: number;
  totalCandles: number;
  /** 1-based position for display (\"candle 12 of 1,440\"). `0` with no candles loaded. */
  position: number;
}

function parseOpenTimeMs(candle: Candle): number | null {
  const ms = Date.parse(candle.open_time);
  return Number.isFinite(ms) ? ms : null;
}

/** Keeps `index` within `[0, length - 1]`, or `0` for an empty array. */
export function clampIndex(index: number, length: number): number {
  if (length <= 0) {
    return 0;
  }
  return Math.min(Math.max(index, 0), length - 1);
}

/**
 * Computes every timeline figure the timeline/status UI needs from the
 * loaded candles and the current position — a pure function so the
 * component and the engine's own tests can both exercise it without a
 * running scheduler.
 */
export function computeTimeline(candles: readonly Candle[], currentIndex: number): ReplayTimeline {
  if (candles.length === 0) {
    return {
      startMs: null,
      endMs: null,
      currentMs: null,
      progress: 0,
      totalCandles: 0,
      position: 0,
    };
  }
  const index = clampIndex(currentIndex, candles.length);
  const startMs = parseOpenTimeMs(candles[0]!);
  const endMs = parseOpenTimeMs(candles[candles.length - 1]!);
  const currentMs = parseOpenTimeMs(candles[index]!);
  const span = startMs !== null && endMs !== null ? endMs - startMs : null;
  let progress: number;
  if (span !== null && span > 0 && currentMs !== null) {
    progress = Math.min(100, Math.max(0, ((currentMs - startMs!) / span) * 100));
  } else if (candles.length > 1) {
    progress = (index / (candles.length - 1)) * 100;
  } else {
    progress = 100;
  }
  return {
    startMs,
    endMs,
    currentMs,
    progress,
    totalCandles: candles.length,
    position: index + 1,
  };
}

/**
 * Finds the index of the candle whose `open_time` is closest to (at or
 * before) `targetMs` — the operation a timeline seek needs. `candles` must
 * already be sorted ascending by `open_time` (guaranteed by the backend's
 * `sort=asc` default and by `fetchAllCandles` never reordering pages).
 * Binary search: O(log n), which matters once a session holds several
 * thousand candles and a slider drag fires many seeks per second.
 */
export function indexForTimestamp(candles: readonly Candle[], targetMs: number): number {
  if (candles.length === 0) {
    return 0;
  }
  let lo = 0;
  let hi = candles.length - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    const ms = parseOpenTimeMs(candles[mid]!);
    if (ms !== null && ms <= targetMs) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return lo;
}

/** Maps a `[0, 100]` slider value back to a candle index — the inverse of `computeTimeline`'s `progress`. */
export function indexForProgress(candles: readonly Candle[], progressPercent: number): number {
  if (candles.length === 0) {
    return 0;
  }
  const clampedProgress = Math.min(100, Math.max(0, progressPercent));
  const startMs = parseOpenTimeMs(candles[0]!);
  const endMs = parseOpenTimeMs(candles[candles.length - 1]!);
  if (startMs === null || endMs === null || endMs === startMs) {
    return clampIndex(Math.round((clampedProgress / 100) * (candles.length - 1)), candles.length);
  }
  const targetMs = startMs + (clampedProgress / 100) * (endMs - startMs);
  return indexForTimestamp(candles, targetMs);
}
