'use client';

import CancelIcon from '@mui/icons-material/Cancel';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import { useExperiment } from '@/features/experiments/hooks/use-experiments-data';
import type { TrainingJob } from '@/types/api/training';
import {
  useCancelTrainingJob,
  useDeleteTrainingJob,
  useRunTrainingJob,
  useTrainingJob,
} from '../hooks/use-training-jobs-data';
import { TRAINING_STATUS_LEGEND } from '../lib/training-job-help';
import { ConfirmActionDialog } from './confirm-action-dialog';
import { TrainingJobLogsPanel } from './training-job-logs-panel';
import { TrainingJobStageTimeline } from './training-job-stage-timeline';
import { TrainingJobStatusChip } from './training-job-status-chip';

export interface TrainingJobDetailDialogProps {
  jobId: string | null;
  onClose: () => void;
}

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '—';
}

function formatDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt || !completedAt) return '—';
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 0 || Number.isNaN(ms)) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function ResultSummaryCard({ job }: { job: TrainingJob }) {
  const experiment = useExperiment(job.experiment_id);
  const summary = job.result_summary;
  const metrics =
    summary && typeof summary.metrics === 'object' && summary.metrics !== null
      ? (summary.metrics as Record<string, unknown>)
      : null;
  const artifactUri =
    summary && typeof summary.artifact_uri === 'string' ? summary.artifact_uri : null;

  return (
    <Stack spacing={0.5}>
      <Typography variant="subtitle2">Result Summary</Typography>
      <Stack spacing={0.25}>
        <Typography variant="body2" color="text.secondary">
          Job ID: <code>{job.id}</code>
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Experiment: {experiment.data?.name ?? job.experiment_id}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Model: {job.model_type}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Dataset: {job.dataset_version ?? 'Not recorded'}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Status: {job.status}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Duration: {formatDuration(job.started_at, job.completed_at)}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Generated: {formatTimestamp(job.completed_at)}
        </Typography>
      </Stack>
      {metrics ? (
        <Stack spacing={0.25}>
          <Typography variant="caption" sx={{ fontWeight: 700 }}>
            Metrics
          </Typography>
          {Object.entries(metrics).map(([name, value]) => (
            <Typography key={name} variant="body2" color="text.secondary">
              {name}: {String(value)}
            </Typography>
          ))}
        </Stack>
      ) : null}
      <Stack spacing={0.25}>
        <Typography variant="caption" sx={{ fontWeight: 700 }}>
          Artifacts
        </Typography>
        {artifactUri ? (
          <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
            {artifactUri}
          </Typography>
        ) : (
          <Typography variant="body2" color="text.secondary">
            None recorded yet.
          </Typography>
        )}
      </Stack>
    </Stack>
  );
}

/**
 * The job's status monitor (an 8-step pipeline timeline, timestamps,
 * lifecycle actions), its full log trail, and its result summary once
 * completed. Polls while `status === "running"` via `useTrainingJob`, so a
 * user watching this dialog sees the pipeline's stages progress without
 * manually refreshing.
 */
export function TrainingJobDetailDialog({ jobId, onClose }: TrainingJobDetailDialogProps) {
  const job = useTrainingJob(jobId);
  const run = useRunTrainingJob();
  const cancel = useCancelTrainingJob();
  const del = useDeleteTrainingJob();
  const [confirming, setConfirming] = useState<'delete' | 'cancel' | null>(null);

  const handleRun = () => jobId && run.mutate(jobId);
  const handleCancelConfirmed = () => {
    if (!jobId) return;
    cancel.mutate(jobId, { onSuccess: () => setConfirming(null) });
  };
  const handleDeleteConfirmed = () => {
    if (!jobId) return;
    del.mutate(jobId, { onSuccess: onClose });
  };

  const data = job.data;
  const mutationError = run.error ?? cancel.error ?? del.error;

  return (
    <>
      <Dialog open={Boolean(jobId)} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>Training Job</DialogTitle>
        <DialogContent>
          {renderDialogBody({ isLoading: job.isLoading, data, mutationError, jobId })}
        </DialogContent>
        <DialogActions>
          <Tooltip title="Delete this training job">
            <span>
              <IconButton
                aria-label="Delete training job"
                onClick={() => setConfirming('delete')}
                disabled={!data || data.status === 'running' || del.isPending}
              >
                <DeleteOutlineIcon />
              </IconButton>
            </span>
          </Tooltip>
          <Box sx={{ flex: 1 }} />
          <Button onClick={onClose}>Close</Button>
          {data?.status === 'pending' || data?.status === 'running' ? (
            <Tooltip title="Cancel this job">
              <span>
                <Button
                  startIcon={<CancelIcon />}
                  onClick={() => setConfirming('cancel')}
                  disabled={cancel.isPending}
                >
                  Cancel
                </Button>
              </span>
            </Tooltip>
          ) : null}
          {data?.status === 'pending' ? (
            <Tooltip title="Execute the training pipeline">
              <span>
                <Button
                  variant="contained"
                  startIcon={<PlayArrowIcon />}
                  onClick={handleRun}
                  disabled={run.isPending}
                >
                  {run.isPending ? 'Running…' : 'Run'}
                </Button>
              </span>
            </Tooltip>
          ) : null}
        </DialogActions>
      </Dialog>

      <ConfirmActionDialog
        open={confirming === 'delete'}
        title="Delete Training Job"
        description="Permanently delete this training job and its log trail? This cannot be undone."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        color="error"
        busy={del.isPending}
        onCancel={() => setConfirming(null)}
        onConfirm={handleDeleteConfirmed}
      />
      <ConfirmActionDialog
        open={confirming === 'cancel'}
        title="Cancel Training Job"
        description="Cancel this job? A cancelled job cannot be run again — you would need to create a new one."
        confirmLabel="Cancel Job"
        busyLabel="Cancelling…"
        color="warning"
        busy={cancel.isPending}
        onCancel={() => setConfirming(null)}
        onConfirm={handleCancelConfirmed}
      />
    </>
  );
}

interface DialogBodyProps {
  isLoading: boolean;
  data: ReturnType<typeof useTrainingJob>['data'];
  mutationError: unknown;
  jobId: string | null;
}

function renderDialogBody({ isLoading, data, mutationError, jobId }: DialogBodyProps) {
  if (isLoading && !data) {
    return (
      <Stack alignItems="center" sx={{ py: 4 }}>
        <CircularProgress size={24} aria-label="Loading training job" />
      </Stack>
    );
  }
  if (data && jobId) {
    return (
      <Stack spacing={2} sx={{ pt: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <TrainingJobStatusChip status={data.status} />
          <InfoTooltip label="Training status" sections={TRAINING_STATUS_LEGEND} />
          <Chip size="small" variant="outlined" label={`Model: ${data.model_type}`} />
          {data.status === 'running' ? (
            <Tooltip title="Refreshing automatically while running">
              <CircularProgress size={14} aria-label="Job running, refreshing" />
            </Tooltip>
          ) : null}
        </Stack>

        <Stack spacing={0.5}>
          <Typography variant="subtitle2">Status Monitor</Typography>
          <TrainingJobStageTimeline status={data.status} currentStage={data.current_stage} />
          <Typography variant="body2" color="text.secondary">
            Started: {formatTimestamp(data.started_at)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Completed: {formatTimestamp(data.completed_at)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Dataset version: {data.dataset_version ?? '—'}
          </Typography>
        </Stack>

        {data.error_message ? (
          <Alert severity="error" role="alert">
            {data.error_message}
          </Alert>
        ) : null}

        {data.result_summary ? <ResultSummaryCard job={data} /> : null}

        <Divider />

        <TrainingJobLogsPanel jobId={jobId} logs={data.logs} status={data.status} />

        {mutationError ? (
          <Alert severity="error" role="alert">
            {mutationError instanceof Error ? mutationError.message : 'Action failed.'}
          </Alert>
        ) : null}
      </Stack>
    );
  }
  return null;
}
