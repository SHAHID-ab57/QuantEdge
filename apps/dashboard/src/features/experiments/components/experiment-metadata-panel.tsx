'use client';

import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import {
  EXPERIMENT_STATUSES,
  type Experiment,
  type ExperimentStatus,
} from '@/types/api/experiments';
import { statusLabel } from '../lib/experiment-status';

export interface ExperimentMetadataPanelProps {
  experiment: Experiment;
  onStatusChange: (status: ExperimentStatus) => void;
  statusUpdating?: boolean;
}

function Field({ label, value, help }: { label: string; value: string; help?: string }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
      <Stack direction="row" spacing={0.25} alignItems="center">
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        {help ? <InfoTooltip label={label} sections={[{ heading: label, body: help }]} /> : null}
      </Stack>
      <Typography
        variant="body2"
        sx={{ fontWeight: 600, textAlign: 'right', wordBreak: 'break-word', maxWidth: '60%' }}
      >
        {value}
      </Typography>
    </Stack>
  );
}

function describeFeatureSet(experiment: Experiment): string {
  if (!experiment.feature_set || experiment.feature_set.length === 0) {
    return 'Not recorded';
  }
  return experiment.feature_set.map((entry) => entry.feature).join(', ');
}

function describeTargetConfig(experiment: Experiment): string {
  if (!experiment.target_config || experiment.target_config.length === 0) {
    return 'Not recorded';
  }
  return experiment.target_config.map((entry) => entry.target).join(', ');
}

function describeSplitConfig(experiment: Experiment): string {
  const split = experiment.split_config;
  if (!split) {
    return 'Not recorded';
  }
  return `${(split.train * 100).toFixed(0)}% / ${(split.validation * 100).toFixed(0)}% / ${(split.test * 100).toFixed(0)}%`;
}

/**
 * The experiment's reproducibility record — dataset version, feature set,
 * target configuration, and split configuration, exactly as recorded at
 * creation time. These fields are deliberately read-only here: an
 * experiment's whole purpose is to say what was actually built and run,
 * so editing them after the fact would misrepresent that record. Status
 * is the one field this panel lets a researcher change, since a status
 * transition (draft → running → completed/failed) is the experiment
 * lifecycle itself, not a correction to history.
 */
export function ExperimentMetadataPanel({
  experiment,
  onStatusChange,
  statusUpdating = false,
}: ExperimentMetadataPanelProps) {
  return (
    <Stack spacing={1.25} aria-label="Experiment metadata">
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="body2" color="text.secondary">
          Status
        </Typography>
        <TextField
          select
          size="small"
          value={experiment.status}
          disabled={statusUpdating}
          onChange={(event) => onStatusChange(event.target.value as ExperimentStatus)}
          slotProps={{ select: { 'aria-label': 'Experiment status' } }}
          sx={{ minWidth: 160 }}
        >
          {EXPERIMENT_STATUSES.map((status) => (
            <MenuItem key={status} value={status}>
              {statusLabel(status)}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <Field
        label="Dataset version"
        value={experiment.dataset_version ?? 'Not recorded'}
        help="The ML Dataset Builder's ml_dataset_id this experiment was built over."
      />
      <Field
        label="Feature set"
        value={describeFeatureSet(experiment)}
        help="The features selected when the dataset for this experiment was built."
      />
      <Field
        label="Target"
        value={describeTargetConfig(experiment)}
        help="The prediction target(s) this experiment's dataset was built with."
      />
      <Field
        label="Split configuration"
        value={describeSplitConfig(experiment)}
        help="Train / validation / test split ratios, in that order."
      />
      <Field label="Model type" value={experiment.model_type ?? 'Not recorded'} />
      <Field label="Created" value={new Date(experiment.created_at).toLocaleString()} />
      <Field label="Last updated" value={new Date(experiment.updated_at).toLocaleString()} />
    </Stack>
  );
}
