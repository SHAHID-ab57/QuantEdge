'use client';

import CancelIcon from '@mui/icons-material/Cancel';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import RestoreIcon from '@mui/icons-material/Restore';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { PredictionListResponse, PredictionSummary } from '@/types/api/prediction';

export interface PredictionHistoryTableProps {
  data: PredictionListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  onPageChange: (page: number) => void;
  onReopen: (prediction: PredictionSummary) => void;
}

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 3 }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={7}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

/** The same Correct/Incorrect glyph `prediction-samples-table.tsx` already
 * renders for a training job's own validation samples — reused here rather
 * than a second, differently-styled way of showing the same idea. */
function renderCorrectness(correct: boolean) {
  return correct ? (
    <CheckCircleIcon fontSize="small" color="success" aria-label="Correct" />
  ) : (
    <CancelIcon fontSize="small" color="error" aria-label="Incorrect" />
  );
}

/**
 * Graded vs. pending, visibly distinct rather than a blank cell:
 * - Pending (`actual_outcome === null`): "Awaiting outcome — available
 *   after <timestamp>", never blank — a viewer should never wonder whether
 *   the outcome is unknown or just hasn't loaded.
 * - Graded, classification: the real outcome plus a Correct/Incorrect glyph.
 * - Graded, regression: the real outcome plus its absolute error.
 */
function renderOutcome(prediction: PredictionSummary) {
  if (prediction.actual_outcome === null) {
    return (
      <Typography variant="caption" color="text.secondary">
        Awaiting outcome
        {prediction.available_after
          ? ` — available after ${new Date(prediction.available_after).toLocaleString()}`
          : null}
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      <Typography variant="body2">{String(prediction.actual_outcome)}</Typography>
      {prediction.is_correct !== null ? renderCorrectness(prediction.is_correct) : null}
      {prediction.error !== null ? (
        <Typography variant="caption" color="text.secondary">
          (error: {prediction.error.toFixed(4)})
        </Typography>
      ) : null}
    </Stack>
  );
}

/**
 * Prediction History's list view — every past `POST /predictions/run` this
 * platform has recorded, most recent first. Mirrors
 * `benchmark-history-table.tsx`'s exact shape (a metadata-only list, Reopen,
 * server-paginated) — the same "history" convention this platform already
 * established for the ML Dataset Builder and Model Evaluation.
 */
export function PredictionHistoryTable({
  data,
  isLoading,
  page,
  limit,
  onPageChange,
  onReopen,
}: PredictionHistoryTableProps) {
  const predictions = data?.predictions ?? [];
  const total = data?.total ?? 0;

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 360 }}>
        <Table stickyHeader aria-label="Prediction history table" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Symbol</TableCell>
              <TableCell>Target</TableCell>
              <TableCell>As Of</TableCell>
              <TableCell>Predicted</TableCell>
              <TableCell align="right">Confidence</TableCell>
              <TableCell>Outcome</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              predictions.map((prediction) => (
                <TableRow key={prediction.id} hover>
                  <TableCell>{prediction.symbol}</TableCell>
                  <TableCell>{prediction.target_column}</TableCell>
                  <TableCell>{new Date(prediction.as_of).toLocaleString()}</TableCell>
                  <TableCell>{String(prediction.predicted_value)}</TableCell>
                  <TableCell align="right">
                    {prediction.confidence !== null ? (
                      <Chip size="small" label={`${(prediction.confidence * 100).toFixed(0)}%`} />
                    ) : (
                      <Typography variant="caption" color="text.secondary">
                        —
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>{renderOutcome(prediction)}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Reopen this prediction">
                      <IconButton
                        size="small"
                        aria-label={`Reopen prediction ${prediction.id}`}
                        onClick={() => onReopen(prediction)}
                      >
                        <RestoreIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
            {!isLoading && predictions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No predictions yet — run one above, and it will appear here.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={total}
        page={page - 1}
        onPageChange={(_, nextPage) => onPageChange(nextPage + 1)}
        rowsPerPage={limit}
        rowsPerPageOptions={[]}
        labelRowsPerPage=""
      />
    </Paper>
  );
}
