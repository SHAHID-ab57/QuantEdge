'use client';

import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
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
import TableSortLabel from '@mui/material/TableSortLabel';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { MLDatasetBuildListParams } from '@/lib/api/ml-datasets';
import type { MLDatasetBuildListResponse, MLDatasetBuildSummary } from '@/types/api/ml-datasets';

type SortColumn = NonNullable<MLDatasetBuildListParams['sort']>;

const COLUMNS: { key: SortColumn; label: string }[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'timeframe', label: 'Timeframe' },
  { key: 'row_count', label: 'Rows' },
  { key: 'created_at', label: 'Built' },
];

export interface DatasetHistoryTableProps {
  data: MLDatasetBuildListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  sort: SortColumn;
  dir: 'asc' | 'desc';
  onPageChange: (page: number) => void;
  onSortChange: (sort: SortColumn, dir: 'asc' | 'desc') => void;
  onSelect: (build: MLDatasetBuildSummary) => void;
  onDelete: (build: MLDatasetBuildSummary) => void;
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
 * Dataset History's list view — every dataset the ML Dataset Builder has
 * built and persisted, most recent first by default. Mirrors
 * `training-jobs-table.tsx`'s exact shape (server-side sort/pagination, a
 * clickable row opening a detail view) — the same convention every
 * paginated list on this platform already follows.
 */
export function DatasetHistoryTable({
  data,
  isLoading,
  page,
  limit,
  sort,
  dir,
  onPageChange,
  onSortChange,
  onSelect,
  onDelete,
}: DatasetHistoryTableProps) {
  const builds = data?.builds ?? [];
  const total = data?.total ?? 0;

  const handleSort = (key: SortColumn) => {
    if (key === sort) {
      onSortChange(key, dir === 'asc' ? 'desc' : 'asc');
    } else {
      onSortChange(key, 'asc');
    }
  };

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 420 }}>
        <Table stickyHeader aria-label="Dataset history table" size="small">
          <TableHead>
            <TableRow>
              {COLUMNS.map((column) => (
                <TableCell key={column.key} sortDirection={sort === column.key ? dir : false}>
                  <TableSortLabel
                    active={sort === column.key}
                    direction={sort === column.key ? dir : 'asc'}
                    onClick={() => handleSort(column.key)}
                  >
                    {column.label}
                  </TableSortLabel>
                </TableCell>
              ))}
              <TableCell>Quality</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              builds.map((build) => (
                <TableRow
                  key={build.id}
                  hover
                  onClick={() => onSelect(build)}
                  sx={{ cursor: 'pointer' }}
                  tabIndex={0}
                  aria-label={`Open ML dataset build ${build.symbol} ${build.timeframe}`}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') onSelect(build);
                  }}
                >
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {build.symbol}
                    </Typography>
                  </TableCell>
                  <TableCell>{build.timeframe}</TableCell>
                  <TableCell>
                    <Tooltip
                      title={`${build.feature_count} feature column(s), ${build.target_count} target column(s)`}
                    >
                      <span>{build.row_count.toLocaleString()}</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell>{formatDate(build.created_at)}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={build.quality_passed ? 'Passed' : 'Failed'}
                      color={build.quality_passed ? 'success' : 'error'}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="Remove from Dataset History">
                      <IconButton
                        size="small"
                        aria-label={`Delete ML dataset build ${build.symbol} ${build.timeframe}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          onDelete(build);
                        }}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
            {!isLoading && builds.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS.length + 2} align="center" sx={{ py: 5 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No datasets built yet — use the builder above, and it will appear here.
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
