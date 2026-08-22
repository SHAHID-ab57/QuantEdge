import type { UTCTimestamp } from 'lightweight-charts';
import { toUnixTime } from '@/components/chart/data-adapter';
import type { Candle } from '@/types/api/market';

/**
 * Client-side synthesis of the *currently forming* candle from streamed
 * trades. The backend has no candle-aggregation pipeline for live ticks
 * (`CandleClosed` bus events are reserved for a future milestone — see
 * `app/events/example_events.py`), so this is the only way to show a
 * live-updating last bar; once a bucket closes, the historical REST
 * candle for it eventually supersedes it via the periodic candle-sync
 * job. See `FRONTEND.md` § "Live Market Dashboard" for the full flow.
 */
export interface LiveCandlePoint {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const TIMEFRAME_PATTERN = /^(\d+)([mhd])$/;
const UNIT_SECONDS: Record<string, number> = { m: 60, h: 3600, d: 86_400 };

/** Bucket length in seconds for a timeframe like `1m`/`5m`/`4h`/`1d`, or `null` if unrecognized. */
export function timeframeSeconds(timeframe: string): number | null {
  const match = TIMEFRAME_PATTERN.exec(timeframe);
  if (!match) {
    return null;
  }
  const amount = Number(match[1]);
  const unitSeconds = UNIT_SECONDS[match[2]!];
  return unitSeconds === undefined ? null : amount * unitSeconds;
}

/** Start-of-bucket UTC second for `epochSeconds` at `bucketSeconds` resolution. */
export function bucketStart(epochSeconds: number, bucketSeconds: number): UTCTimestamp {
  return (Math.floor(epochSeconds / bucketSeconds) * bucketSeconds) as UTCTimestamp;
}

/**
 * Converts the newest stored candle into a seed for the forming bar, so the
 * live bar continues the chart's history instead of starting from scratch
 * (see `useLiveCandle`). Returns `null` for a missing or unparseable candle
 * — a bad seed must degrade to "no continuity", never to a NaN bar that
 * would corrupt the chart's price scale.
 */
export function toLiveCandlePoint(candle: Candle | undefined): LiveCandlePoint | null {
  if (!candle) {
    return null;
  }
  const time = toUnixTime(candle.open_time);
  if (time === null) {
    return null;
  }
  const values = [candle.open, candle.high, candle.low, candle.close, candle.volume].map(Number);
  if (values.some((value) => !Number.isFinite(value))) {
    return null;
  }
  const [open, high, low, close, volume] = values as [number, number, number, number, number];
  return { time, open, high, low, close, volume };
}

export interface LiveTradeInput {
  price: number;
  size: number;
  /** Trade time as whole UTC seconds (see `toUnixTime` in the chart's `data-adapter.ts`). */
  eventTimeSeconds: number;
}

/**
 * Folds one trade into the current forming candle for `timeframe`.
 *
 * Same bucket: high/low/close/volume update in place. A new bucket opens
 * at the previous candle's close (continuity with the chart's last bar)
 * unless there is no previous candle yet, in which case the trade's own
 * price opens it. Returns `current` unchanged if `timeframe` isn't
 * recognized, so callers never have to guard against `null` themselves.
 */
export function applyTradeToCandle(
  current: LiveCandlePoint | null,
  trade: LiveTradeInput,
  timeframe: string,
): LiveCandlePoint | null {
  const seconds = timeframeSeconds(timeframe);
  if (seconds === null) {
    return current;
  }
  const time = bucketStart(trade.eventTimeSeconds, seconds);

  if (current && current.time === time) {
    return {
      time,
      open: current.open,
      high: Math.max(current.high, trade.price),
      low: Math.min(current.low, trade.price),
      close: trade.price,
      volume: current.volume + trade.size,
    };
  }

  const open = current ? current.close : trade.price;
  return {
    time,
    open,
    high: Math.max(open, trade.price),
    low: Math.min(open, trade.price),
    close: trade.price,
    volume: trade.size,
  };
}
