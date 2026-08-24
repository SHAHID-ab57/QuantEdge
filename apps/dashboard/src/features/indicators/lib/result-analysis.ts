import type { IndicatorSeries } from '@/types/api/indicators';
import type { IndicatorKnowledge, IndicatorState } from './indicator-knowledge';

export type TrendDirection = 'up' | 'down' | 'flat';

/** Whether the latest visible point has a computed value yet. Almost always `'computed'` — the engine never returns a series with no value at all — kept explicit rather than assumed. */
export type IndicatorStatus = 'computed' | 'warming-up';

export interface SeriesSummary {
  name: string;
  label: string;
  latest: number | null;
  previous: number | null;
  absoluteChange: number | null;
  percentChange: number | null;
  trend: TrendDirection | null;
  /**
   * A descriptive classification of the latest value, only when the
   * indicator has an established convention for one (e.g. RSI's 30/70
   * thresholds). `null` for every indicator without one — deliberately
   * never synthesized from trend direction: "the average is rising" is
   * not itself a reading of market state, and labeling it one would be
   * exactly the kind of trading signal this page does not generate.
   */
  state: IndicatorState | null;
  status: IndicatorStatus;
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
 * Reduces one computed series down to what a researcher checks first:
 * where it stands now, where it stood before, how much it moved, and
 * (only when the indicator itself defines a reading) its descriptive
 * state — computed once here rather than scattered across the summary
 * and chart components that both need it.
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
  const state = latest !== null && knowledge.classifyState ? knowledge.classifyState(latest) : null;
  const status: IndicatorStatus = latest !== null ? 'computed' : 'warming-up';

  return {
    name: series.name,
    label: series.label,
    latest,
    previous,
    absoluteChange,
    percentChange,
    trend,
    state,
    status,
  };
}
