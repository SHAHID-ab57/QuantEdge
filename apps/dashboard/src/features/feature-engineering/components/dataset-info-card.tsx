'use client';

import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import type { FeatureDataset } from '@/types/api/features';

export interface DatasetInfoCardProps {
  dataset: FeatureDataset;
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
 * Dataset identity and versioning at a glance — the record a researcher
 * would quote when asking "which exact dataset produced this model?"
 *
 * Deliberately separate from `DatasetSummary` (which covers *quality*: rows
 * dropped, nulls, gaps, failures): this card is about *identity and
 * reproducibility* — the fields that answer "what is this, and can it be
 * reproduced" rather than "is it trustworthy." Keeping the two apart
 * mirrors how the backend itself separates `FeatureDataset`'s provenance
 * fields from its `quality: DatasetQualityReport`.
 */
export function DatasetInfoCard({ dataset }: DatasetInfoCardProps) {
  return (
    <Stack spacing={1.25} aria-label="Dataset information">
      <Field
        label="Dataset ID"
        value={dataset.dataset_id}
        monospace
        help="Uniquely identifies this exact build. Rebuilding the identical request later produces a new ID — a dataset is a snapshot, not a live view, so each build is its own reproducible record even if the underlying candles haven't changed."
      />
      <Field
        label="Pipeline Version"
        value={dataset.meta.pipeline_version}
        help="The execution pipeline's own version — bumped when the pipeline itself changes in a way that could affect any feature's output, independent of any single feature's own version."
      />
      <Field label="Market" value={dataset.symbol} />
      <Field label="Timeframe" value={dataset.timeframe} />
      <Field label="Rows" value={dataset.meta.total_rows.toLocaleString()} />
      <Field label="Columns" value={String(dataset.columns.length)} />
      <Field
        label="Generation Time"
        value={`${dataset.quality.generation_time_ms.toFixed(1)} ms`}
        help="Wall-clock time spent running every requested feature generator over the loaded candles — not counting the database load, which is reported separately."
      />
    </Stack>
  );
}
