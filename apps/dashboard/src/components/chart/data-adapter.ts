import type { CandlestickData, HistogramData, UTCTimestamp } from 'lightweight-charts';
import type { Candle } from '@/types/api/market';

export interface ChartTheme {
  upColor: string;
  downColor: string;
}

export interface ChartSeriesData {
  candlesticks: CandlestickData[];
  volume: HistogramData[];
  /** Candles dropped because a field was missing, non-finite, or non-parseable. */
  skipped: number;
}

/**
 * Converts an ISO-8601 timestamp to a lightweight-charts `UTCTimestamp`
 * (whole seconds since epoch). Returns `null` for anything unparseable so
 * callers can drop the point instead of feeding `NaN` into the chart.
 */
export function toUnixTime(iso: string): UTCTimestamp | null {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) {
    return null;
  }
  return Math.floor(ms / 1000) as UTCTimestamp;
}

function parseFinite(value: string | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Transforms backend `Candle` rows (string OHLCV, ISO timestamps) into the
 * numeric, UTC-second-keyed series lightweight-charts expects. This is the
 * only place API shape meets chart-library shape (Objective #9's
 * `DataAdapter`), so backend field renames only ever touch this file.
 *
 * Defensive by design (Objective #11 "Unexpected data"): a candle with a
 * missing/non-numeric field, an unparseable timestamp, or a timestamp that
 * duplicates one already seen is skipped rather than crashing the chart.
 * Output is always sorted ascending by time, which lightweight-charts
 * requires.
 */
export function toChartSeries(candles: readonly Candle[], theme: ChartTheme): ChartSeriesData {
  const seen = new Set<number>();
  const candlesticks: CandlestickData[] = [];
  const volume: HistogramData[] = [];
  let skipped = 0;

  for (const candle of candles) {
    const time = toUnixTime(candle.open_time);
    const open = parseFinite(candle.open);
    const high = parseFinite(candle.high);
    const low = parseFinite(candle.low);
    const close = parseFinite(candle.close);
    const rawVolume = parseFinite(candle.volume);

    if (
      time === null ||
      open === null ||
      high === null ||
      low === null ||
      close === null ||
      rawVolume === null ||
      seen.has(time)
    ) {
      skipped += 1;
      continue;
    }

    seen.add(time);
    candlesticks.push({ time, open, high, low, close });
    volume.push({ time, value: rawVolume, color: close >= open ? theme.upColor : theme.downColor });
  }

  candlesticks.sort((left, right) => Number(left.time) - Number(right.time));
  volume.sort((left, right) => Number(left.time) - Number(right.time));

  return { candlesticks, volume, skipped };
}
