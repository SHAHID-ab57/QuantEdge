'use client';

import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import NextLink from 'next/link';
import { InfoTooltip } from '@/components/info-tooltip';
import {
  describeFeatureSet,
  describePredictionHorizon,
  describeSplitConfig,
  describeTargetConfig,
} from '@/features/experiments/components/experiment-metadata-panel';
import type { Experiment } from '@/types/api/experiments';

export interface TrainingSummaryPanelProps {
  experiment: Experiment | null;
  datasetVersion: string;
  modelLabel: string | null;
  symbol?: string;
  timeframe?: string;
}

function MissingChip({ label }: { label: string }) {
  return <Chip size="small" color="warning" variant="outlined" label={label} />;
}

function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ maxWidth: '65%' }}>
        {children}
      </Stack>
    </Stack>
  );
}

/**
 * A live preview of exactly what this job will train for, shown before
 * submission — the create dialog's fields all feed into it, so a
 * researcher can see the whole picture in one glance rather than piecing
 * it together from several form controls. Warning chips mark anything
 * missing rather than silently showing a blank, since a job created
 * without a dataset version or model is guaranteed to fail once run.
 */
export function TrainingSummaryPanel({
  experiment,
  datasetVersion,
  modelLabel,
  symbol,
  timeframe,
}: TrainingSummaryPanelProps) {
  const horizon = experiment ? describePredictionHorizon(experiment) : null;
  const featureCount = experiment?.feature_set?.length ?? null;

  return (
    <Stack
      spacing={1}
      sx={{ p: 1.5, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}
      aria-label="Training summary"
    >
      <Typography variant="subtitle2">Summary</Typography>

      <SummaryRow label="Experiment">
        {experiment ? (
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {experiment.name}
          </Typography>
        ) : (
          <MissingChip label="Not selected" />
        )}
      </SummaryRow>

      <SummaryRow label="Dataset version">
        {datasetVersion ? (
          <Typography variant="body2" noWrap title={datasetVersion}>
            {datasetVersion}
          </Typography>
        ) : (
          <MissingChip label="Missing" />
        )}
      </SummaryRow>

      <SummaryRow label="Target">
        {experiment ? (
          <Typography variant="body2">{describeTargetConfig(experiment)}</Typography>
        ) : (
          <MissingChip label="Select an experiment" />
        )}
      </SummaryRow>

      {symbol || timeframe ? (
        <SummaryRow label="Market">
          <Typography variant="body2">
            {symbol || '—'} {timeframe ? `(${timeframe})` : ''}
          </Typography>
        </SummaryRow>
      ) : null}

      <SummaryRow label="Model">
        {modelLabel ? (
          <Typography variant="body2">{modelLabel}</Typography>
        ) : (
          <MissingChip label="Not selected" />
        )}
      </SummaryRow>

      <SummaryRow label="Split">
        <Typography variant="body2">
          {experiment ? describeSplitConfig(experiment) : 'Select an experiment'}
        </Typography>
      </SummaryRow>

      <SummaryRow label="Feature count">
        <Typography variant="body2" title={experiment ? describeFeatureSet(experiment) : undefined}>
          {featureCount === null ? 'Select an experiment' : featureCount}
        </Typography>
      </SummaryRow>

      <SummaryRow label="Prediction horizon">
        <Typography variant="body2">{horizon ?? 'Not recorded'}</Typography>
      </SummaryRow>

      <SummaryRow label="Estimated dataset size">
        <Typography variant="body2" color="text.secondary">
          Not tracked
        </Typography>
        <InfoTooltip
          label="Estimated dataset size"
          sections={[
            {
              heading: 'Why this is unknown',
              body: 'The ML Dataset Builder never persists a dataset to a table, so row counts against a dataset_version citation are not tracked anywhere on this platform.',
            },
          ]}
        />
      </SummaryRow>

      <SummaryRow label="Validation status">
        <Typography variant="body2" color="text.secondary">
          Unknown
        </Typography>
        <InfoTooltip
          label="Validation status"
          sections={[
            {
              heading: 'Why this is unknown',
              body: 'This platform does not persist a per-dataset-version validated flag. Run Dataset Validation separately and use its report to judge whether this dataset is trustworthy before running the job.',
            },
          ]}
        />
      </SummaryRow>

      <Typography variant="caption" color="text.secondary">
        Run{' '}
        <Link component={NextLink} href="/validation">
          Dataset Validation
        </Link>{' '}
        first if you have not already reviewed this dataset&apos;s quality report.
      </Typography>
    </Stack>
  );
}
