'use client';

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
import { InfoTooltip } from '@/components/info-tooltip';
import type { TrainingJobListParams } from '@/lib/api/training';
import type { TrainingJobListResponse, TrainingJobSummary } from '@/types/api/training';
import { TRAINING_STATUS_LEGEND } from '../lib/training-job-help';
import { stageLabel } from '../lib/training-job-status';
import { TrainingJobStatusChip } from './training-job-status-chip';

type SortColumn = NonNullable<TrainingJobListParams['sort']>;

const COLUMNS: { key: SortColumn; label: string }[] = [
  { key: 'model_type', label: 'Model Type' },
  { key: 'status', label: 'Status' },
  { key: 'created_at', label: 'Created' },
  { key: 'updated_at', label: 'Updated' },
];

export interface TrainingJobsTableProps {
  data: TrainingJobListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  sort: SortColumn;
  dir: 'asc' | 'desc';
  onPageChange: (page: number) => void;
  onSortChange: (sort: SortColumn, dir: 'asc' | 'desc') => void;
  onSelect: (job: TrainingJobSummary) => void;
  /** Whether any experiment exists at all — distinguishes "nothing matches this
   * filter" from "there is nothing to create a job for yet." */
  hasExperiments?: boolean;
}

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 5 }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={COLUMNS.length + 3}>
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
 * The training job list: sortable columns (server-side, via the backend's
 * whitelisted `sort`/`dir`) and paginated rows, mirroring
 * `experiments-table.tsx`'s own shape. Each row opens the detail dialog
 * (status monitor, logs, result summary) rather than navigating away.
 */
export function TrainingJobsTable({
  data,
  isLoading,
  page,
  limit,
  sort,
  dir,
  onPageChange,
  onSortChange,
  onSelect,
  hasExperiments = true,
}: TrainingJobsTableProps) {
  const jobs = data?.jobs ?? [];
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
      <TableContainer sx={{ maxHeight: 560 }}>
        <Table stickyHeader aria-label="Training jobs table" size="small">
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
                  {column.key === 'status' ? (
                    <InfoTooltip label="Training status" sections={TRAINING_STATUS_LEGEND} />
                  ) : null}
                </TableCell>
              ))}
              <TableCell>Stage</TableCell>
              <TableCell>Dataset Version</TableCell>
              <TableCell align="right">Logs</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              jobs.map((job: TrainingJobSummary) => (
                <TableRow
                  key={job.id}
                  hover
                  onClick={() => onSelect(job)}
                  sx={{ cursor: 'pointer' }}
                  tabIndex={0}
                  aria-label={`Open training job ${job.model_type}`}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') onSelect(job);
                  }}
                >
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {job.model_type}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <TrainingJobStatusChip status={job.status} />
                  </TableCell>
                  <TableCell>{formatDate(job.created_at)}</TableCell>
                  <TableCell>{formatDate(job.updated_at)}</TableCell>
                  <TableCell>{stageLabel(job.current_stage)}</TableCell>
                  <TableCell>
                    <Tooltip title={job.dataset_version ?? 'No dataset version recorded'}>
                      <Typography
                        variant="body2"
                        noWrap
                        sx={{ maxWidth: 160, display: 'inline-block' }}
                      >
                        {job.dataset_version ?? '—'}
                      </Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right">{job.log_count}</TableCell>
                </TableRow>
              ))
            )}
            {!isLoading && jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS.length + 3} align="center" sx={{ py: 5 }}>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    role="status"
                    aria-label={hasExperiments ? 'No training jobs found' : 'No experiments exist'}
                  >
                    {hasExperiments
                      ? 'No training jobs match this filter.'
                      : 'No experiments exist yet — create one before registering a training job.'}
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
