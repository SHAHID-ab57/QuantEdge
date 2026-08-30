'use client';

import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import type { FeatureStatistics } from '@/types/api/features';

export interface FeatureStatisticsPanelProps {
  statistics: FeatureStatistics;
}

function formatNumber(value: number | null): string {
  return value === null ? '—' : Number(value.toPrecision(6)).toString();
}

/**
 * Per-column count/nulls/mean/std/min/max over the *complete* built
 * dataset — `GET .../features/statistics`'s response. Deliberately distinct
 * from `ColumnStatsPopover` (which computes the same shape of statistic
 * client-side, but only over whatever rows are currently rendered in the
 * preview, explicitly caveated as such via its own `isPreviewSubset` prop):
 * that popover answers "what does the column I'm looking at right now show,
 * for a quick glance," this panel answers "what does the entire dataset's
 * column look like," the same "preview vs. export" distinction this
 * platform already draws for CSV/JSON downloads. A categorical/boolean
 * column shows `—` for `mean`/`std`/`minimum`/`maximum` rather than a
 * fabricated number — the same gate the backend's own `compute_dataset_statistics`
 * and this module's `column-stats.ts` both apply.
 */
export function FeatureStatisticsPanel({ statistics }: FeatureStatisticsPanelProps) {
  if (statistics.columns.length === 0) return null;

  return (
    <TableContainer>
      <Table size="small" aria-label="Full dataset statistics">
        <TableHead>
          <TableRow>
            <TableCell>Column</TableCell>
            <TableCell align="right">Count</TableCell>
            <TableCell align="right">Nulls</TableCell>
            <TableCell align="right">Mean</TableCell>
            <TableCell align="right">Std Dev</TableCell>
            <TableCell align="right">Min</TableCell>
            <TableCell align="right">Max</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {statistics.columns.map((column) => (
            <TableRow key={column.column}>
              <TableCell sx={{ fontWeight: 600 }}>{column.column}</TableCell>
              <TableCell align="right">{column.count.toLocaleString()}</TableCell>
              <TableCell align="right">{column.null_count.toLocaleString()}</TableCell>
              <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {formatNumber(column.mean)}
              </TableCell>
              <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {formatNumber(column.std)}
              </TableCell>
              <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {formatNumber(column.minimum)}
              </TableCell>
              <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {formatNumber(column.maximum)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', pt: 0.5 }}>
        Computed over all {statistics.row_count.toLocaleString()} rows in the complete dataset.
      </Typography>
    </TableContainer>
  );
}
