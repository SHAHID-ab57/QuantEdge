'use client';

import EditIcon from '@mui/icons-material/Edit';
import Button from '@mui/material/Button';
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
  /** Opens `ExperimentConfigDialog` — see that component's own docstring. */
  onEditConfig: () => void;
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

/**
 * Reused wherever a compact, human-readable summary of an experiment's
 * reproducibility record is needed outside this panel itself — e.g. the
 * Training Job creation dialog's auto-populated, read-only summary (see
 * `features/ml-training/components/experiment-summary-fields.tsx`) — so
 * "how a feature set/target/split reads as text" has exactly one
 * definition on this platform.
 */
export function describeFeatureSet(experiment: Experiment): string {
  if (!experiment.feature_set || experiment.feature_set.length === 0) {
    return 'Not recorded';
  }
  return experiment.feature_set.map((entry) => entry.feature).join(', ');
}

export function describeTargetConfig(experiment: Experiment): string {
  if (!experiment.target_config || experiment.target_config.length === 0) {
    return 'Not recorded';
  }
  return experiment.target_config.map((entry) => entry.target).join(', ');
}

export function describeSplitConfig(experiment: Experiment): string {
  const split = experiment.split_config;
  if (!split) {
    return 'Not recorded';
  }
  return `${(split.train * 100).toFixed(0)}% / ${(split.validation * 100).toFixed(0)}% / ${(split.test * 100).toFixed(0)}%`;
}

/** The first recorded target's `horizon` parameter, if any target config declares one. */
export function describePredictionHorizon(experiment: Experiment): string | null {
  for (const entry of experiment.target_config ?? []) {
    const horizon = entry.params?.horizon;
    if (horizon !== undefined) return horizon;
  }
  return null;
}

/**
 * The experiment's reproducibility record — dataset version, feature set,
 * target configuration, and split configuration. Dataset version is set at
 * creation time and shown read-only here. Feature set/target/split are
 * editable via "Edit configuration" (`ExperimentConfigDialog`): before that
 * dialog existed, the only way to set them was a hand-written
 * `curl -X PATCH`, so most experiments simply never had them recorded — a
 * training job could reach `Run` several pipeline stages deep before
 * discovering that. Status is the other field this panel lets a researcher
 * change directly, since a status transition (draft → running →
 * completed/failed) is the experiment lifecycle itself, not a correction
 * to history.
 */
export function ExperimentMetadataPanel({
  experiment,
  onStatusChange,
  onEditConfig,
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
      <Button
        size="small"
        variant="outlined"
        startIcon={<EditIcon fontSize="small" />}
        onClick={onEditConfig}
        sx={{ alignSelf: 'flex-start' }}
      >
        Edit configuration
      </Button>
      <Field label="Model type" value={experiment.model_type ?? 'Not recorded'} />
      <Field label="Created" value={new Date(experiment.created_at).toLocaleString()} />
      <Field label="Last updated" value={new Date(experiment.updated_at).toLocaleString()} />
    </Stack>
  );
}
