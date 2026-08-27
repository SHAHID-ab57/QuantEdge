'use client';

import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';

export interface TrainValTestMetricsTableProps {
  trainMetrics: unknown;
  validationMetrics: unknown;
  testMetrics: unknown;
  overfitting: unknown;
}

function isMetricsRecord(value: unknown): value is Record<string, number> {
  return (
    typeof value === 'object' &&
    value !== null &&
    Object.values(value as Record<string, unknown>).every((v) => typeof v === 'number')
  );
}

function isOverfittingReport(
  value: unknown,
): value is { flagged: boolean; gap: number; threshold: number; message: string } {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as Record<string, unknown>).flagged === 'boolean' &&
    typeof (value as Record<string, unknown>).message === 'string'
  );
}

/**
 * Train / Validation / Test metrics side by side, with an overfitting banner
 * when the backend's `compute_overfitting_flag` (train metric far exceeding
 * the held-out one) fires. Any split missing from `result_summary` (the
 * placeholder adapter has none of these) renders as an empty column rather
 * than hiding the whole table, since validation metrics alone are still
 * useful to see in this shape.
 */
export function TrainValTestMetricsTable({
  trainMetrics,
  validationMetrics,
  testMetrics,
  overfitting,
}: TrainValTestMetricsTableProps) {
  const train = isMetricsRecord(trainMetrics) ? trainMetrics : null;
  const validation = isMetricsRecord(validationMetrics) ? validationMetrics : null;
  const test =
    isMetricsRecord(testMetrics) && Object.keys(testMetrics).length > 0 ? testMetrics : null;
  const overfittingReport = isOverfittingReport(overfitting) ? overfitting : null;

  if (!train && !validation && !test) {
    return null;
  }

  const metricNames = Array.from(
    new Set([
      ...Object.keys(train ?? {}),
      ...Object.keys(validation ?? {}),
      ...Object.keys(test ?? {}),
    ]),
  );

  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        Train / Validation / Test Metrics
      </Typography>
      <TableContainer>
        <Table size="small" aria-label="Train, validation, and test metrics">
          <TableHead>
            <TableRow>
              <TableCell>Metric</TableCell>
              <TableCell align="right">Train</TableCell>
              <TableCell align="right">Validation</TableCell>
              <TableCell align="right">Test</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {metricNames.map((name) => (
              <TableRow key={name}>
                <TableCell sx={{ textTransform: 'capitalize' }}>{name}</TableCell>
                <TableCell align="right">{train?.[name]?.toFixed(4) ?? '—'}</TableCell>
                <TableCell align="right">{validation?.[name]?.toFixed(4) ?? '—'}</TableCell>
                <TableCell align="right">{test?.[name]?.toFixed(4) ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {overfittingReport ? (
        <Alert
          severity={overfittingReport.flagged ? 'warning' : 'success'}
          icon={overfittingReport.flagged ? <WarningAmberIcon fontSize="small" /> : undefined}
        >
          {overfittingReport.message}
        </Alert>
      ) : null}
    </Stack>
  );
}
