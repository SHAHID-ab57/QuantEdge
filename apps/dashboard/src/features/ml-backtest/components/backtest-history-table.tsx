'use client';

import RestoreIcon from '@mui/icons-material/Restore';
import Chip, { type ChipProps } from '@mui/material/Chip';
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
import type { BacktestListResponse, BacktestStatus, BacktestSummary } from '@/types/api/backtest';

export interface BacktestHistoryTableProps {
  data: BacktestListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  onPageChange: (page: number) => void;
  onReopen: (run: BacktestSummary) => void;
}

const STATUS_COLORS: Record<BacktestStatus, ChipProps['color']> = {
  pending: 'default',
  running: 'info',
  completed: 'success',
  failed: 'error',
};

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
 * Backtest History's list view — every past `POST /backtests/run` this
 * platform has recorded, most recent first. Mirrors
 * `benchmark-history-table.tsx`'s exact shape (a metadata-only list, Reopen,
 * server-paginated) — the same "history" convention this platform already
 * established, minus a Delete action (no `DELETE /backtests/{id}` exists).
 */
export function BacktestHistoryTable({
  data,
  isLoading,
  page,
  limit,
  onPageChange,
  onReopen,
}: BacktestHistoryTableProps) {
  const runs = data?.runs ?? [];
  const total = data?.total ?? 0;

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 360 }}>
        <Table stickyHeader aria-label="Backtest history table" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Symbol</TableCell>
              <TableCell>Step</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Steps</TableCell>
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              runs.map((run) => (
                <TableRow key={run.id} hover>
                  <TableCell>{run.symbol}</TableCell>
                  <TableCell>{run.step}</TableCell>
                  <TableCell>
                    <Chip size="small" color={STATUS_COLORS[run.status]} label={run.status} />
                  </TableCell>
                  <TableCell align="right">
                    {run.completed_steps}/{run.total_steps}
                    {run.truncated ? ' *' : ''}
                  </TableCell>
                  <TableCell>{new Date(run.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Reopen this backtest">
                      <IconButton
                        size="small"
                        aria-label={`Reopen backtest ${run.id}`}
                        onClick={() => onReopen(run)}
                      >
                        <RestoreIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
            {!isLoading && runs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No past backtests yet — run one above, and it will appear here.
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
