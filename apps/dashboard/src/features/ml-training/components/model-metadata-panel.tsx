'use client';

import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

export interface ModelMetadataPanelProps {
  metadata: unknown;
}

interface ParsedModelMetadata {
  sklearn_version: string;
  joblib_version: string;
  training_duration_seconds: number;
  cpu_time_seconds: number;
  memory_usage_mb: number | null;
  feature_count: number;
  sample_count: number;
}

function isModelMetadata(value: unknown): value is ParsedModelMetadata {
  const v = value as Record<string, unknown> | null;
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof v.sklearn_version === 'string' &&
    typeof v.joblib_version === 'string' &&
    typeof v.feature_count === 'number' &&
    typeof v.sample_count === 'number'
  );
}

/**
 * Library versions, timing, memory, and dataset shape for one training run
 * (`collect_model_metadata`) — the Model Metadata requirement. Renders
 * nothing for the placeholder adapter, which records no such metadata.
 */
export function ModelMetadataPanel({ metadata }: ModelMetadataPanelProps) {
  const parsed = isModelMetadata(metadata) ? metadata : null;
  if (!parsed) return null;

  const rows: Array<[string, string]> = [
    ['scikit-learn version', parsed.sklearn_version],
    ['joblib version', parsed.joblib_version],
    ['Training duration', `${parsed.training_duration_seconds.toFixed(3)}s`],
    ['CPU time', `${parsed.cpu_time_seconds.toFixed(3)}s`],
    [
      'Memory usage',
      parsed.memory_usage_mb !== null ? `${parsed.memory_usage_mb.toFixed(1)} MB` : 'Unknown',
    ],
    ['Feature count', String(parsed.feature_count)],
    ['Sample count', String(parsed.sample_count)],
  ];

  return (
    <Stack spacing={0.25}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        Model Metadata
      </Typography>
      {rows.map(([label, value]) => (
        <Stack key={label} direction="row" justifyContent="space-between">
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
          <Typography variant="body2">{value}</Typography>
        </Stack>
      ))}
    </Stack>
  );
}
