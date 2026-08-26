'use client';

import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import type { MLDatasetResponse } from '@/types/api/ml-datasets';

export interface MLDatasetInfoCardProps {
  dataset: MLDatasetResponse;
}

function Field({
  label,
  value,
  help,
  monospace = false,
}: {
  label: string;
  value: string;
  help?: string;
  monospace?: boolean;
}) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
      <Stack direction="row" spacing={0.25} alignItems="center">
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        {help ? <InfoTooltip label={label} sections={[{ heading: label, body: help }]} /> : null}
      </Stack>
      <Typography
        variant="body2"
        sx={{
          fontWeight: 600,
          fontFamily: monospace ? 'monospace' : undefined,
          fontVariantNumeric: 'tabular-nums',
          textAlign: 'right',
          wordBreak: 'break-all',
        }}
      >
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * The ML dataset's identity and versioning chain — the record a researcher
 * would quote when asking "which exact artifact trained this model?"
 *
 * Mirrors `feature-engineering/components/dataset-info-card.tsx`'s split
 * between identity (this card) and quality (`MLDatasetSummary`), extended
 * with the layers unique to an ML artifact: a fresh `ml_dataset_id` on top
 * of the underlying feature build's own `dataset_id`, the target pipeline's
 * version, and this composition's own builder version — see
 * `ARCHITECTURE.md` § "ML Dataset Builder" for why each layer is versioned
 * independently.
 */
export function MLDatasetInfoCard({ dataset }: MLDatasetInfoCardProps) {
  const { meta, split_bounds: splitBounds, split_ratios: splitRatios } = dataset;
  return (
    <Stack spacing={1.25} aria-label="ML dataset information">
      <Field
        label="ML Dataset ID"
        value={dataset.ml_dataset_id}
        monospace
        help="Uniquely identifies this exact ML artifact — feature build, target generation, validation, and split all bundled together. Rebuilding the identical request later produces a new ID."
      />
      <Field
        label="Dataset ID"
        value={dataset.dataset_id}
        monospace
        help="The underlying feature build's own identity."
      />
      <Field label="Market" value={dataset.symbol} />
      <Field label="Timeframe" value={dataset.timeframe} />
      <Field label="Builder Version" value={meta.builder_version} />
      <Field label="Pipeline Version" value={meta.pipeline_version} />
      <Field label="Target Pipeline Version" value={meta.target_pipeline_version} />
      <Field label="Rows" value={meta.total_rows.toLocaleString()} />
      <Field label="Feature Columns" value={String(dataset.feature_columns.length)} />
      <Field label="Target Columns" value={String(dataset.target_columns.length)} />
      <Field
        label="Split"
        value={`${splitRatios.train} / ${splitRatios.validation} / ${splitRatios.test}`}
        help="Train / validation / test fractions, applied as a contiguous chronological slice — never shuffled."
      />
      <Field
        label="Split rows"
        value={`${splitBounds.train_rows.toLocaleString()} / ${splitBounds.validation_rows.toLocaleString()} / ${splitBounds.test_rows.toLocaleString()}`}
      />
    </Stack>
  );
}
