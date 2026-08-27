'use client';

import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';

export interface ConfusionMatrixDetail {
  class: unknown;
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
  support: number;
}

export interface ConfusionMatrixDetailsTableProps {
  details: unknown;
}

function isConfusionMatrixDetails(value: unknown): value is ConfusionMatrixDetail[] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        typeof row === 'object' &&
        row !== null &&
        typeof (row as Record<string, unknown>).true_positive === 'number' &&
        typeof (row as Record<string, unknown>).support === 'number',
    )
  );
}

/**
 * Per-class True/False Positive/Negative counts and support — the one-vs-rest
 * breakdown behind the raw confusion matrix grid, from
 * `compute_confusion_details`. A classification-only view; renders nothing
 * for a regressor or the placeholder adapter.
 */
export function ConfusionMatrixDetailsTable({ details }: ConfusionMatrixDetailsTableProps) {
  const rows = isConfusionMatrixDetails(details) ? details : null;
  if (!rows || rows.length === 0) {
    return null;
  }

  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        Confusion Matrix Details
      </Typography>
      <TableContainer>
        <Table size="small" aria-label="Confusion matrix details">
          <TableHead>
            <TableRow>
              <TableCell>Class</TableCell>
              <TableCell align="right">True Positive</TableCell>
              <TableCell align="right">False Positive</TableCell>
              <TableCell align="right">True Negative</TableCell>
              <TableCell align="right">False Negative</TableCell>
              <TableCell align="right">Support</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={index}>
                <TableCell>{String(row.class)}</TableCell>
                <TableCell align="right">{row.true_positive}</TableCell>
                <TableCell align="right">{row.false_positive}</TableCell>
                <TableCell align="right">{row.true_negative}</TableCell>
                <TableCell align="right">{row.false_negative}</TableCell>
                <TableCell align="right">{row.support}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}
