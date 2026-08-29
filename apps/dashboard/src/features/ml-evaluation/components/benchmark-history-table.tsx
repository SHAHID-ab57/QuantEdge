'use client';

import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
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
import type { BenchmarkRunListResponse, BenchmarkRunSummary } from '@/types/api/evaluation';

export interface BenchmarkHistoryTableProps {
  data: BenchmarkRunListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  onPageChange: (page: number) => void;
  onReopen: (run: BenchmarkRunSummary) => void;
  onDelete: (run: BenchmarkRunSummary) => void;
}

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 3 }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={5}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

/**
 * Benchmark History's list view — every past `POST /evaluation/benchmark`
 * comparison this platform has recorded, most recent first. Mirrors
 * `dataset-history-table.tsx`'s exact shape (a metadata-only list, Reopen
 * and Delete actions, server-paginated) — the same "history" convention
 * this platform already established for the ML Dataset Builder.
 */
export function BenchmarkHistoryTable({
  data,
  isLoading,
  page,
  limit,
  onPageChange,
  onReopen,
  onDelete,
}: BenchmarkHistoryTableProps) {
  const runs = data?.runs ?? [];
  const total = data?.total ?? 0;

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 360 }}>
        <Table stickyHeader aria-label="Benchmark history table" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Dataset Version</TableCell>
              <TableCell>Target Column</TableCell>
              <TableCell align="right">Candidates</TableCell>
              <TableCell>Compared</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              runs.map((run) => (
                <TableRow key={run.id} hover>
                  <TableCell>{run.dataset_version ?? '—'}</TableCell>
                  <TableCell>{run.target_column ?? '—'}</TableCell>
                  <TableCell align="right">
                    <Chip size="small" label={run.candidate_count} />
                  </TableCell>
                  <TableCell>{new Date(run.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Reopen this comparison">
                      <IconButton
                        size="small"
                        aria-label={`Reopen benchmark run ${run.id}`}
                        onClick={() => onReopen(run)}
                      >
                        <RestoreIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Remove from Benchmark History">
                      <IconButton
                        size="small"
                        aria-label={`Delete benchmark run ${run.id}`}
                        onClick={() => onDelete(run)}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
            {!isLoading && runs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No past comparisons yet — run one above, and it will appear here.
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
