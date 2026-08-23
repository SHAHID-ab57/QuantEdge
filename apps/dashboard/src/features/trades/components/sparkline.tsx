'use client';

import { memo, useMemo } from 'react';

export interface SparklineProps {
  /** Oldest to newest. A `null` entry is a gap — skipped when drawing, not plotted as zero. */
  values: (number | null)[];
  width?: number;
  height?: number;
  /** Any CSS/SVG color, e.g. an MUI theme color resolved beforehand — this component takes no theme dependency. */
  color?: string;
  ariaLabel: string;
}

const DEFAULT_WIDTH = 120;
const DEFAULT_HEIGHT = 32;
const STROKE_WIDTH = 1.5;

/**
 * Points are spaced evenly by *index*, not by their real timestamp gaps —
 * the right simplification for a small trend indicator where "is it going
 * up or down" matters far more than exact time spacing, and it keeps this
 * component a pure function of `values` alone.
 */
function buildPath(values: (number | null)[], width: number, height: number): string | null {
  let min = Infinity;
  let max = -Infinity;
  for (const value of values) {
    if (value !== null) {
      if (value < min) min = value;
      if (value > max) max = value;
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return null;
  }
  const range = max - min;
  const denominator = Math.max(values.length - 1, 1);
  const points: string[] = [];
  values.forEach((value, index) => {
    if (value === null) {
      return;
    }
    const x = (index / denominator) * width;
    const y = range === 0 ? height / 2 : height - ((value - min) / range) * height;
    points.push(`${points.length === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`);
  });
  return points.length >= 2 ? points.join(' ') : null;
}

/**
 * A tiny, dependency-free SVG line — deliberately not a `lightweight-charts`
 * instance (that library is the right tool for the full candlestick chart
 * elsewhere in this codebase, not for a few dozen points in a stat tile).
 * Re-rendering a plain SVG `<path>` on new data is itself the "incremental"
 * update this component needs: there is no persistent chart-engine instance
 * to tear down and recreate, so the usual "don't recreate the chart" concern
 * for a heavier charting library doesn't apply here in the first place. The
 * path string is memoized on the `values` reference so an unrelated parent
 * re-render (e.g. a sibling tile changing) never recomputes it.
 */
function SparklineInner({
  values,
  width = DEFAULT_WIDTH,
  height = DEFAULT_HEIGHT,
  color = 'currentColor',
  ariaLabel,
}: SparklineProps) {
  const path = useMemo(() => buildPath(values, width, height), [values, width, height]);

  if (!path) {
    return (
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${ariaLabel}: not enough data yet`}
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke={color}
          strokeOpacity={0.25}
          strokeWidth={STROKE_WIDTH}
        />
      </svg>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${width} ${height}`}
    >
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={STROKE_WIDTH}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export const Sparkline = memo(SparklineInner);
