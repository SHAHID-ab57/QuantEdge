'use client';

import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import type { MLDatasetResponse } from '@/types/api/ml-datasets';
import { EXPORT_FORMAT_OPTIONS } from '../lib/export-format';

export interface MLDatasetMetadataPanelProps {
  dataset: MLDatasetResponse;
  /** The submitted date range, in human-readable form — not carried by the response itself. */
  dataRangeText: string;
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
 * A dedicated card answering "what exactly produced this file, and where
 * did it come from" in one place — deliberately separate from
 * `MLDatasetInfoCard` (versioning chain, for reproducibility) and
 * `MLDatasetSummary` (quality/trust). This one is the record a researcher
 * would attach to a model card or a lab notebook entry: source, engine,
 * and generation identity, nothing about row counts or trust.
 *
 * `Validation Report ID` uses the embedded `ValidationReport`'s own
 * `dataset_id` — the validation engine does not mint an independent report
 * ID of its own, so a report is identified by the dataset it validated
 * (see `app/dataset_validation/report.py`). This is stated honestly here
 * rather than fabricating a separate ID field the backend doesn't have.
 */
export function MLDatasetMetadataPanel({ dataset, dataRangeText }: MLDatasetMetadataPanelProps) {
  const targetGenerators = dataset.targets.map((info) => info.label).join(', ') || 'None';

  return (
    <Stack spacing={1.25} aria-label="ML dataset metadata">
      <Field label="Dataset UUID" value={dataset.ml_dataset_id} monospace />
      <Field label="Feature Pipeline Version" value={dataset.meta.pipeline_version} />
      <Field
        label="Validation Report ID"
        value={dataset.validation.dataset_id}
        monospace
        help="The validation engine identifies a report by the dataset_id it validated, not a separate report ID."
      />
      <Field label="Source Market" value={dataset.symbol} />
      <Field label="Source Timeframe" value={dataset.timeframe} />
      <Field label="Source Date Range" value={dataRangeText} />
      <Field label="Generated Timestamp" value={dataset.meta.generated_at} />
      <Field
        label="Engine Version"
        value={dataset.validation.engine_version}
        help="The validation engine's own version, independent of any single rule's."
      />
      <Field label="Target Generator" value={targetGenerators} />
      <Field label="Splitter" value="ChronologicalSplitter" />
      <Field
        label="Export Formats"
        value={EXPORT_FORMAT_OPTIONS.map((option) => option.label).join(', ')}
      />
    </Stack>
  );
}
