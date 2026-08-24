/**
 * Pure SVG line-path math shared by every small, dependency-free chart in
 * this codebase — the Trade Analytics `Sparkline` and the Technical
 * Indicators `IndicatorChart`. Promoted out of `Sparkline` once a second
 * component needed the identical "plot these values against a shared
 * domain" math, rather than a second copy of the same formula.
 *
 * Deliberately not a real charting library: these are a handful of points
 * rendered as a single SVG `<path>`, re-computed on every render rather
 * than an incremental update against a persistent chart-engine instance —
 * the right tool for a small on-page visualization, not a replacement for
 * the `lightweight-charts` candlestick module elsewhere in this codebase.
 */

export interface LineDomain {
  min: number;
  max: number;
}

/**
 * The value range spanned by one or more series, optionally widened by
 * extra fixed values (e.g. reference-line levels that must stay visible
 * even if no series value reaches them). Returns `null` when every input
 * is empty or entirely `null` — there is no domain to plot against.
 */
export function computeDomain(
  valueSets: readonly (number | null)[][],
  extra: readonly number[] = [],
): LineDomain | null {
  let min = Infinity;
  let max = -Infinity;
  for (const values of valueSets) {
    for (const value of values) {
      if (value !== null) {
        if (value < min) min = value;
        if (value > max) max = value;
      }
    }
  }
  for (const value of extra) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return null;
  }
  return { min, max };
}

/**
 * Points are spaced evenly by *index*, not by real timestamp gaps — the
 * right simplification for a small trend visualization where "is it going
 * up or down" matters far more than exact time spacing.
 */
export function buildLinePath(
  values: readonly (number | null)[],
  width: number,
  height: number,
  domain: LineDomain,
): string | null {
  const range = domain.max - domain.min;
  const denominator = Math.max(values.length - 1, 1);
  const points: string[] = [];
  values.forEach((value, index) => {
    if (value === null) {
      return;
    }
    const x = (index / denominator) * width;
    const y = yForValue(value, height, domain, range);
    points.push(`${points.length === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`);
  });
  return points.length >= 2 ? points.join(' ') : null;
}

/** The y-coordinate a single value maps to within `domain`, for drawing a reference line. */
export function yForValue(
  value: number,
  height: number,
  domain: LineDomain,
  range: number = domain.max - domain.min,
): number {
  return range === 0 ? height / 2 : height - ((value - domain.min) / range) * height;
}
