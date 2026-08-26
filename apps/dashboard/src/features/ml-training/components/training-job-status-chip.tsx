'use client';

import Chip from '@mui/material/Chip';
import Tooltip from '@mui/material/Tooltip';
import type { TrainingJobStatus } from '@/types/api/training';
import { STATUS_COLORS, statusLabel } from '../lib/training-job-status';
import { TRAINING_STATUS_HELP } from '../lib/training-job-help';

export function TrainingJobStatusChip({ status }: { status: TrainingJobStatus }) {
  return (
    <Tooltip title={TRAINING_STATUS_HELP[status].body} enterTouchDelay={0}>
      <Chip size="small" color={STATUS_COLORS[status]} label={statusLabel(status)} />
    </Tooltip>
  );
}
