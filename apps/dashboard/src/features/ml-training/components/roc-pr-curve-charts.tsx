'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

export interface RocPrCurveChartsProps {
  rocPrCurves: unknown;
}

interface CurvePair {
  fpr: number[];
  tpr: number[];
  precision: number[];
  recall: number[];
}

interface ParsedRocPr {
  curves: Record<string, CurvePair>;
  auc: Record<string, number>;
  macroAuc: number | null;
}

const CHART_WIDTH = 220;
const CHART_HEIGHT = 200;
const SERIES_COLORS = ['#4f9cff', '#ff8a4f', '#59c78a', '#c77dff', '#ffd54f'];

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((v) => typeof v === 'number');
}

function parseRocPr(value: unknown): ParsedRocPr | null {
  if (typeof value !== 'object' || value === null) return null;
  const raw = value as Record<string, unknown>;
  const curvesRaw = raw.curves;
  const aucRaw = raw.auc;
  if (typeof curvesRaw !== 'object' || curvesRaw === null) return null;
  const curves: Record<string, CurvePair> = {};
  for (const [label, curve] of Object.entries(curvesRaw as Record<string, unknown>)) {
    if (typeof curve !== 'object' || curve === null) continue;
    const c = curve as Record<string, unknown>;
    const roc = c.roc as Record<string, unknown> | undefined;
    const pr = c.pr as Record<string, unknown> | undefined;
    if (!roc || !pr) continue;
    if (
      isNumberArray(roc.fpr) &&
      isNumberArray(roc.tpr) &&
      isNumberArray(pr.precision) &&
      isNumberArray(pr.recall)
    ) {
      curves[label] = { fpr: roc.fpr, tpr: roc.tpr, precision: pr.precision, recall: pr.recall };
    }
  }
  if (Object.keys(curves).length === 0) return null;
  const auc: Record<string, number> = {};
  if (typeof aucRaw === 'object' && aucRaw !== null) {
    for (const [label, value_] of Object.entries(aucRaw as Record<string, unknown>)) {
      if (typeof value_ === 'number') auc[label] = value_;
    }
  }
  const macroAuc = typeof raw.macro_auc === 'number' ? raw.macro_auc : null;
  return { curves, auc, macroAuc };
}

function pathFor(xs: number[], ys: number[]): string {
  return xs
    .map((x, index) => {
      const y = ys[index];
      if (y === undefined) return '';
      const svgX = x * CHART_WIDTH;
      const svgY = CHART_HEIGHT - y * CHART_HEIGHT;
      return `${index === 0 ? 'M' : 'L'}${svgX.toFixed(1)},${svgY.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(' ');
}

/**
 * One-vs-rest ROC and Precision-Recall curves, one line per class, plotted as
 * plain SVG polylines (this codebase's established "small on-page chart,
 * not a charting library" approach — see `src/lib/svg-line-path.ts`). Values
 * are always in [0, 1] by construction, so the domain is fixed rather than
 * computed. Renders nothing for a regression job (no `roc_pr_curves` key).
 */
export function RocPrCurveCharts({ rocPrCurves }: RocPrCurveChartsProps) {
  const parsed = parseRocPr(rocPrCurves);
  if (!parsed) return null;
  const labels = Object.keys(parsed.curves);

  return (
    <Stack spacing={1}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        ROC &amp; Precision-Recall Curves
      </Typography>
      <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
        <Stack spacing={0.5} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            ROC Curve
          </Typography>
          <Box
            component="svg"
            width={CHART_WIDTH}
            height={CHART_HEIGHT}
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            role="img"
            aria-label="ROC curve"
          >
            <line
              x1={0}
              y1={CHART_HEIGHT}
              x2={CHART_WIDTH}
              y2={0}
              stroke="#888"
              strokeDasharray="4 4"
            />
            {labels.map((label, index) => {
              const curve = parsed.curves[label];
              if (!curve) return null;
              return (
                <path
                  key={label}
                  d={pathFor(curve.fpr, curve.tpr)}
                  fill="none"
                  stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
                  strokeWidth={2}
                />
              );
            })}
          </Box>
        </Stack>
        <Stack spacing={0.5} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Precision-Recall Curve
          </Typography>
          <Box
            component="svg"
            width={CHART_WIDTH}
            height={CHART_HEIGHT}
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            role="img"
            aria-label="Precision-Recall curve"
          >
            {labels.map((label, index) => {
              const curve = parsed.curves[label];
              if (!curve) return null;
              return (
                <path
                  key={label}
                  d={pathFor(curve.recall, curve.precision)}
                  fill="none"
                  stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
                  strokeWidth={2}
                />
              );
            })}
          </Box>
        </Stack>
      </Stack>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        {labels.map((label, index) => {
          const auc = parsed.auc[label];
          return (
            <Typography
              key={label}
              variant="caption"
              sx={{ color: SERIES_COLORS[index % SERIES_COLORS.length] }}
            >
              {label}: AUC {auc !== undefined ? auc.toFixed(3) : '—'}
            </Typography>
          );
        })}
        {parsed.macroAuc !== null ? (
          <Typography variant="caption" color="text.secondary">
            Macro AUC: {parsed.macroAuc.toFixed(3)}
          </Typography>
        ) : null}
      </Stack>
    </Stack>
  );
}
