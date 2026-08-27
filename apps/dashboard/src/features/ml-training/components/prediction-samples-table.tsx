'use client';

import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';

export interface PredictionSample {
  actual: unknown;
  predicted: unknown;
  probability: number | null;
  confidence_level: string | null;
  correct: boolean | null;
}

export interface PredictionSamplesTableProps {
  samples: unknown;
}

function isPredictionSamples(value: unknown): value is PredictionSample[] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        typeof row === 'object' &&
        row !== null &&
        'actual' in row &&
        'predicted' in row &&
        'confidence_level' in row,
    )
  );
}

function confidenceColor(level: string | null): 'success' | 'warning' | 'default' {
  if (level === 'high') return 'success';
  if (level === 'medium') return 'warning';
  return 'default';
}

function formatCell(value: unknown): string {
  if (typeof value === 'number') return value.toFixed(4);
  return String(value);
}

function renderCorrectness(correct: boolean | null) {
  if (correct === true) {
    return <CheckCircleIcon fontSize="small" color="success" aria-label="Correct" />;
  }
  if (correct === false) {
    return <CancelIcon fontSize="small" color="error" aria-label="Incorrect" />;
  }
  return '—';
}

/**
 * The Prediction Confidence / Prediction Inspection view: Actual, Predicted,
 * Probability, Confidence Level, and Correct/Incorrect, one row per sample —
 * capped server-side (`build_prediction_samples`'s `cap`) so this never
 * tries to render an entire validation split. For a regression job,
 * probability/confidence/correct are `null` on every row and render as "—"
 * rather than a fabricated value.
 */
export function PredictionSamplesTable({ samples }: PredictionSamplesTableProps) {
  const rows = isPredictionSamples(samples) ? samples : null;
  if (!rows || rows.length === 0) {
    return null;
  }
  const isClassification = rows[0]?.confidence_level !== null;

  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        Prediction Samples
      </Typography>
      <TableContainer>
        <Table size="small" aria-label="Prediction samples">
          <TableHead>
            <TableRow>
              <TableCell>Actual</TableCell>
              <TableCell>Predicted</TableCell>
              {isClassification ? <TableCell align="right">Probability</TableCell> : null}
              {isClassification ? <TableCell>Confidence</TableCell> : null}
              {isClassification ? <TableCell align="center">Correct</TableCell> : null}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={index}>
                <TableCell>{formatCell(row.actual)}</TableCell>
                <TableCell>{formatCell(row.predicted)}</TableCell>
                {isClassification ? (
                  <TableCell align="right">
                    {row.probability !== null ? row.probability.toFixed(3) : '—'}
                  </TableCell>
                ) : null}
                {isClassification ? (
                  <TableCell>
                    {row.confidence_level ? (
                      <Chip
                        size="small"
                        label={row.confidence_level}
                        color={confidenceColor(row.confidence_level)}
                        sx={{ textTransform: 'capitalize' }}
                      />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                ) : null}
                {isClassification ? (
                  <TableCell align="center">{renderCorrectness(row.correct)}</TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}
