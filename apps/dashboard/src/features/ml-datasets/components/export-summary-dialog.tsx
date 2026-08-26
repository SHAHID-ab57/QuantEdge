'use client';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { SplitRatios } from '@/types/api/ml-datasets';
import { estimateExportBytes, formatBytes, EXPORT_FORMAT_OPTIONS } from '../lib/export-format';

export interface ExportSummaryDialogProps {
  open: boolean;
  format: 'csv' | 'json' | null;
  rows: number;
  columns: number;
  targetColumns: readonly string[];
  splitRatios: SplitRatios;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600, textAlign: 'right' }}>
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * A confirmation step before an export actually downloads — rows,
 * columns, targets, split, format, and an approximate file size, so a
 * researcher knows what they're about to download before committing to
 * it, rather than discovering the shape of the file only after it lands
 * in their downloads folder.
 *
 * Reads `EXPORT_FORMAT_OPTIONS` rather than naming "CSV"/"JSON" directly,
 * so a future export format needs no change here.
 */
export function ExportSummaryDialog({
  open,
  format,
  rows,
  columns,
  targetColumns,
  splitRatios,
  busy = false,
  onConfirm,
  onCancel,
}: ExportSummaryDialogProps) {
  if (format === null) {
    return null;
  }
  const option = EXPORT_FORMAT_OPTIONS.find((entry) => entry.format === format);
  const approxBytes = estimateExportBytes(rows, columns, format);

  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>Export Summary</DialogTitle>
      <DialogContent>
        <Stack spacing={1} sx={{ pt: 1 }}>
          <Row label="Rows" value={rows.toLocaleString()} />
          <Row label="Columns" value={columns.toLocaleString()} />
          <Row label="Target" value={targetColumns.join(', ') || 'None'} />
          <Row
            label="Split"
            value={`${(splitRatios.train * 100).toFixed(0)}% / ${(splitRatios.validation * 100).toFixed(0)}% / ${(splitRatios.test * 100).toFixed(0)}%`}
          />
          <Row label="Format" value={option?.label ?? format.toUpperCase()} />
          <Row label="Approximate size" value={formatBytes(approxBytes)} />
          <Typography variant="caption" color="text.secondary">
            Size is a rough estimate, not an exact byte count.
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button variant="contained" onClick={onConfirm} disabled={busy}>
          {busy ? 'Exporting…' : 'Export'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
