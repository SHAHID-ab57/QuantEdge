'use client';

import RestoreIcon from '@mui/icons-material/Restore';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
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
          <TableCell colSpan={6}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
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
                <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
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
