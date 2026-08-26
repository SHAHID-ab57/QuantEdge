'use client';

import Chip from '@mui/material/Chip';
import type { ExperimentStatus } from '@/types/api/experiments';
import { STATUS_COLORS, statusLabel } from '../lib/experiment-status';

export function ExperimentStatusChip({ status }: { status: ExperimentStatus }) {
  return <Chip size="small" color={STATUS_COLORS[status]} label={statusLabel(status)} />;
}
