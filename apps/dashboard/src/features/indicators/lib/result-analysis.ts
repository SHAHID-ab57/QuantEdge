import type { IndicatorSeries } from '@/types/api/indicators';
import type { IndicatorKnowledge, SignalTone } from './indicator-knowledge';

export type TrendDirection = 'up' | 'down' | 'flat';

export interface SeriesSummary {
  name: string;
  label: string;
  latest: number | null;
  previous: number | null;
  absoluteChange: number | null;
  percentChange: number | null;
  trend: TrendDirection | null;
  signal: SignalTone | null;
}

/** Scans from the end for the last two non-null values, newest first. */
function lastTwoNonNull(values: readonly (number | null)[]): [number | null, number | null] {
  let latest: number | null = null;
  let previous: number | null = null;
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = values[index] ?? null;
    if (value === null) {
      continue;
    }
    if (latest === null) {
      latest = value;
    } else {
      previous = value;
      break;
    }
  }
  return [latest, previous];
}

function trendOf(latest: number | null, previous: number | null): TrendDirection | null {
  if (latest === null || previous === null) {
    return null;
  }
  if (latest > previous) return 'up';
  if (latest < previous) return 'down';
  return 'flat';
}

/**
 * The signal a knowledge base entry's `classifySignal` gives when it has
 * one (e.g. RSI's 30/70 thresholds), or a trend-direction fallback when it
 * doesn't: rising reads bullish, falling reads bearish, flat reads
 * neutral. The fallback is deliberately generic rather than omitted —
 * every indicator's value is still comparable to its own recent past even
 * without curated thresholds.
 */
function signalOf(
  latest: number | null,
  trend: TrendDirection | null,
  knowledge: IndicatorKnowledge,
): SignalTone | null {
  if (latest !== null && knowledge.classifySignal) {
    return knowledge.classifySignal(latest);
  }
  if (trend === null) {
    return null;
  }
  if (trend === 'up') return 'bullish';
  if (trend === 'down') return 'bearish';
  return 'neutral';
}

/**
 * Reduces one computed series down to what a researcher checks first:
 * where it stands now, where it stood before, how much it moved, and how
 * to read that movement — computed once here rather than scattered across
 * the summary and chart components that both need it.
 */
export function summarizeSeries(
  series: IndicatorSeries,
  knowledge: IndicatorKnowledge,
): SeriesSummary {
  const [latest, previous] = lastTwoNonNull(series.values);
  const absoluteChange = latest !== null && previous !== null ? latest - previous : null;
  const percentChange =
    absoluteChange !== null && previous !== null && previous !== 0
      ? (absoluteChange / Math.abs(previous)) * 100
      : null;
  const trend = trendOf(latest, previous);
  const signal = signalOf(latest, trend, knowledge);

  return {
    name: series.name,
    label: series.label,
    latest,
    previous,
    absoluteChange,
    percentChange,
    trend,
    signal,
  };
}
