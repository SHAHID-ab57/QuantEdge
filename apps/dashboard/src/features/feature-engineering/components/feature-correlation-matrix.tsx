'use client';

import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import type { FeatureCorrelation } from '@/types/api/features';

export interface FeatureCorrelationMatrixProps {
  correlation: FeatureCorrelation;
}

/** A green/red intensity scale, this codebase's established "plain `sx`
 * background color, not a charting library" approach (the same convention
 * `dataset-preview-table.tsx`'s own split-label coloring already uses). A
 * value near 0 gets no tint; a strong positive correlation tints green, a
 * strong negative one tints red — reading the sign never requires a legend. */
function cellColor(value: number): string {
  const intensity = Math.min(Math.abs(value), 1);
  if (intensity < 0.05) return 'transparent';
  const alpha = 0.12 + intensity * 0.55;
  return value > 0 ? `rgba(76, 175, 80, ${alpha})` : `rgba(244, 67, 54, ${alpha})`;
}

/**
 * Pairwise Pearson correlation across a built dataset's numeric columns —
 * `GET .../features/correlation`'s response, rendered as a heatmap table.
 * Renders nothing when fewer than two numeric columns were compared (the
 * backend's own honest "not enough to correlate" result, not an error) —
 * the same "gracefully absent, not a placeholder" convention
 * `RocPrCurveCharts` already established for a job with no probabilities.
 */
export function FeatureCorrelationMatrix({ correlation }: FeatureCorrelationMatrixProps) {
  if (correlation.columns.length < 2) return null;

  return (
    <TableContainer>
      <Table size="small" aria-label="Feature correlation matrix">
        <TableHead>
          <TableRow>
            <TableCell />
            {correlation.columns.map((name) => (
              <TableCell key={name} align="center">
                {name}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {correlation.columns.map((rowName, rowIndex) => (
            <TableRow key={rowName}>
              <TableCell sx={{ fontWeight: 600 }}>{rowName}</TableCell>
              {correlation.columns.map((columnName, columnIndex) => {
                const value = correlation.matrix[rowIndex]?.[columnIndex] ?? 0;
                return (
                  <TableCell
                    key={columnName}
                    align="center"
                    sx={{ bgcolor: cellColor(value), fontVariantNumeric: 'tabular-nums' }}
                  >
                    {value.toFixed(2)}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', pt: 0.5 }}>
        {correlation.row_count.toLocaleString()} rows compared
      </Typography>
    </TableContainer>
  );
}
