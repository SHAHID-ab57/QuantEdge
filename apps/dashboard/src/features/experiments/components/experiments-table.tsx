'use client';

import Chip from '@mui/material/Chip';
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
import TableSortLabel from '@mui/material/TableSortLabel';
import Typography from '@mui/material/Typography';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ExperimentListParams } from '@/lib/api/experiments';
import type { ExperimentListResponse, ExperimentSummary } from '@/types/api/experiments';
import { ExperimentStatusChip } from './experiment-status-chip';

type SortColumn = NonNullable<ExperimentListParams['sort']>;

const COLUMNS: { key: SortColumn; label: string; align?: 'right' }[] = [
  { key: 'name', label: 'Name' },
  { key: 'status', label: 'Status' },
  { key: 'model_type', label: 'Model Type' },
  { key: 'created_at', label: 'Created' },
  { key: 'updated_at', label: 'Updated' },
];

export interface ExperimentsTableProps {
  data: ExperimentListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  sort: SortColumn;
  dir: 'asc' | 'desc';
  onPageChange: (page: number) => void;
  onSortChange: (sort: SortColumn, dir: 'asc' | 'desc') => void;
}

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 5 }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={COLUMNS.length + 2}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

/**
 * The experiment registry's list view: sortable columns (server-side sort,
 * via `onSortChange` → the backend's own whitelisted `sort`/`dir` query
 * params) and paginated rows (`TablePagination`, the same component
 * `history/components/candles-table.tsx` already uses for the identical
 * limit/offset shape). Each row links to its detail page rather than
 * requiring a separate "View" action.
 */
export function ExperimentsTable({
  data,
  isLoading,
  page,
  limit,
  sort,
  dir,
  onPageChange,
  onSortChange,
}: ExperimentsTableProps) {
  const experiments = data?.experiments ?? [];
  const total = data?.total ?? 0;
  const router = useRouter();

  const handleSort = (key: SortColumn) => {
    if (key === sort) {
      onSortChange(key, dir === 'asc' ? 'desc' : 'asc');
    } else {
      onSortChange(key, 'asc');
    }
  };

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 560 }}>
        <Table stickyHeader aria-label="Experiments table" size="small">
          <TableHead>
            <TableRow>
              {COLUMNS.map((column) => (
                <TableCell
                  key={column.key}
                  align={column.align}
                  sortDirection={sort === column.key ? dir : false}
                >
                  <TableSortLabel
                    active={sort === column.key}
                    direction={sort === column.key ? dir : 'asc'}
                    onClick={() => handleSort(column.key)}
                  >
                    {column.label}
                  </TableSortLabel>
                </TableCell>
              ))}
              <TableCell>Tags</TableCell>
              <TableCell align="right">Metrics</TableCell>
              <TableCell align="right">Artifacts</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              experiments.map((experiment: ExperimentSummary) => (
                <TableRow
                  key={experiment.id}
                  hover
                  onClick={() => router.push(`/experiments/${experiment.id}`)}
                  sx={{ cursor: 'pointer' }}
                >
                  <TableCell>
                    <Link
                      href={`/experiments/${experiment.id}`}
                      style={{ color: 'inherit', textDecoration: 'none' }}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {experiment.name}
                      </Typography>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <ExperimentStatusChip status={experiment.status} />
                  </TableCell>
                  <TableCell>{experiment.model_type ?? '—'}</TableCell>
                  <TableCell>{formatDate(experiment.created_at)}</TableCell>
                  <TableCell>{formatDate(experiment.updated_at)}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {experiment.tags.map((tag) => (
                        <Chip key={tag} size="small" variant="outlined" label={tag} />
                      ))}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">{experiment.metric_count}</TableCell>
                  <TableCell align="right">{experiment.artifact_count}</TableCell>
                </TableRow>
              ))
            )}
            {!isLoading && experiments.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS.length + 3} align="center" sx={{ py: 5 }}>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    role="status"
                    aria-label="No experiments found"
                  >
                    No experiments match this search/filter.
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
