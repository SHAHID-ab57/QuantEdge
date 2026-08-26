'use client';

import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { statusLabel } from '../lib/training-job-status';

export interface TrainingJobFiltersValue {
  experimentId: string;
  status: string;
}

export interface TrainingJobFiltersBarProps {
  value: TrainingJobFiltersValue;
  onChange: (next: TrainingJobFiltersValue) => void;
  statuses: string[];
  experiments: { id: string; name: string }[];
}

export function TrainingJobFiltersBar({
  value,
  onChange,
  statuses,
  experiments,
}: TrainingJobFiltersBarProps) {
  return (
    <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
      <TextField
        select
        size="small"
        label="Experiment"
        value={value.experimentId}
        onChange={(event) => onChange({ ...value, experimentId: event.target.value })}
        sx={{ minWidth: 220 }}
        slotProps={{ select: { displayEmpty: true } }}
      >
        <MenuItem value="">All experiments</MenuItem>
        {experiments.map((experiment) => (
          <MenuItem key={experiment.id} value={experiment.id}>
            {experiment.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        size="small"
        label="Status"
        value={value.status}
        onChange={(event) => onChange({ ...value, status: event.target.value })}
        sx={{ minWidth: 160 }}
        slotProps={{ select: { displayEmpty: true } }}
      >
        <MenuItem value="">All statuses</MenuItem>
        {statuses.map((status) => (
          <MenuItem key={status} value={status}>
            {statusLabel(status)}
          </MenuItem>
        ))}
      </TextField>
    </Stack>
  );
}
