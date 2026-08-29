'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { BenchmarkCandidate } from '@/types/api/evaluation';

export interface MetricComparisonChartProps {
  metricName: string;
  candidates: BenchmarkCandidate[];
}

const CHART_WIDTH = 260;
const BAR_HEIGHT = 22;
const BAR_GAP = 6;
const SERIES_COLORS = ['#4f9cff', '#ff8a4f', '#59c78a', '#c77dff', '#ffd54f'];

/**
 * One horizontal bar per candidate that recorded this metric — plain SVG
 * rectangles, this codebase's established "small on-page chart, not a
 * charting library" approach (see `src/lib/svg-line-path.ts`, used by the
 * line-based charts elsewhere; a benchmark's per-candidate comparison is a
 * categorical bar, not a series over a shared x-axis, so it draws its own
 * simple rects rather than reusing that line-path math). Bars scale against
 * the largest value among the candidates shown, not a fixed [0, 1] domain —
 * a regression metric like RMSE can exceed 1.
 */
export function MetricComparisonChart({ metricName, candidates }: MetricComparisonChartProps) {
  const rows = candidates
    .filter((c) => c.metrics[metricName] !== undefined)
    .map((c) => ({
      label: c.model_type,
      jobId: c.training_job_id,
      value: c.metrics[metricName] as number,
    }));
  if (rows.length === 0) return null;

  const maxValue = Math.max(...rows.map((r) => r.value), 0.0001);
  const height = rows.length * (BAR_HEIGHT + BAR_GAP);

  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase' }}>
        {metricName}
      </Typography>
      <Box
        component="svg"
        width={CHART_WIDTH}
        height={height}
        viewBox={`0 0 ${CHART_WIDTH} ${height}`}
        role="img"
        aria-label={`${metricName} comparison across ${rows.length} models`}
      >
        {rows.map((row, index) => {
          const barWidth = Math.max((row.value / maxValue) * (CHART_WIDTH - 60), 1);
          const y = index * (BAR_HEIGHT + BAR_GAP);
          return (
            <g key={row.jobId}>
              <rect
                x={0}
                y={y}
                width={barWidth}
                height={BAR_HEIGHT}
                fill={SERIES_COLORS[index % SERIES_COLORS.length]}
                rx={3}
              />
              <text x={barWidth + 6} y={y + BAR_HEIGHT / 2 + 4} fontSize={11} fill="currentColor">
                {row.value.toFixed(3)}
              </text>
              <text x={4} y={y + BAR_HEIGHT / 2 + 4} fontSize={10} fill="#0b1220" opacity={0.85}>
                {row.label}
              </text>
            </g>
          );
        })}
      </Box>
    </Stack>
  );
}
