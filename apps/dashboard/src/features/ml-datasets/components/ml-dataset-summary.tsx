'use client';

import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import type { MLDatasetResponse } from '@/types/api/ml-datasets';
import { EXPORT_FORMAT_OPTIONS } from '../lib/export-format';

export interface MLDatasetSummaryProps {
  dataset: MLDatasetResponse;
  /** The submitted date range, in human-readable form (e.g. "All history" or an explicit start–end) — not carried by the response itself. */
  dataRangeText: string;
  /** Target name → "Classification"/"Regression", resolved from the target catalogue; omitted entries just don't show a type chip. */
  targetProblemTypes?: Record<string, string>;
}

function Metric({ label, value, help }: { label: string; value: string; help?: string }) {
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
        sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}
      >
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * How trustworthy this ML dataset is, and what was done about it — the
 * target-side counterpart to `feature-engineering/components/dataset-summary.tsx`.
 *
 * Leads with an **Overview** block (validation status, created-at, split
 * strategy, data range, features/targets selected, export formats,
 * original vs. final row counts) that a researcher would otherwise have
 * to reconstruct by cross-referencing several other panels — identity and
 * version fields specifically (Dataset ID, Pipeline/Builder versions) are
 * deliberately *not* repeated here, since `MLDatasetInfoCard` already
 * shows them directly above this panel and duplicating them would only
 * risk the two drifting apart.
 *
 * Below Overview, two independently-reported trim reasons matter, and
 * conflating them would hide *why* a row is missing: `rows_dropped_warmup`
 * (a feature was not yet defined — the same reason a plain feature
 * dataset drops rows) and `rows_dropped_horizon` (a target's future
 * candle does not exist yet — the leakage-prevention trim unique to this
 * builder). A researcher asking "why do I have fewer rows than candles"
 * needs to know which of the two applies, or that both do.
 */
export function MLDatasetSummary({
  dataset,
  dataRangeText,
  targetProblemTypes = {},
}: MLDatasetSummaryProps) {
  const { meta, quality, targets, target_failures: targetFailures } = dataset;

  const originalRows = meta.total_rows + meta.rows_dropped_warmup + meta.rows_dropped_horizon;
  const problemTypes = Array.from(
    new Set(
      targets
        .map((info) => targetProblemTypes[info.target])
        .filter((value): value is string => Boolean(value)),
    ),
  );
  const predictionTargetText =
    targets.length === 0
      ? 'None'
      : targets.map((info) => `${info.label} (h=${info.horizon})`).join(', ');

  return (
    <Stack spacing={1.25} aria-label="ML dataset summary">
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
        Overview
      </Typography>
      <Metric
        label="Validation status"
        value={dataset.validation.passed ? 'Passed' : 'Failed'}
        help="False only when the embedded validation report found at least one error-severity issue."
      />
      <Metric label="Created at" value={meta.created_at} />
      <Metric
        label="Split strategy"
        value="Chronological (train → validation → test)"
        help="Contiguous time-ordered slices — never shuffled."
      />
      <Metric label="Data range" value={dataRangeText} />
      <Metric label="Prediction target" value={predictionTargetText} />
      <Metric
        label="Target type"
        value={problemTypes.length > 0 ? problemTypes.join(', ') : 'Unknown'}
      />
      <Metric label="Features selected" value={dataset.features.length.toLocaleString()} />
      <Metric
        label="Export formats"
        value={EXPORT_FORMAT_OPTIONS.map((option) => option.label).join(', ')}
      />
      <Metric
        label="Original rows"
        value={originalRows.toLocaleString()}
        help="Rows before warmup and horizon trimming were applied."
      />
      <Metric label="Final rows" value={meta.total_rows.toLocaleString()} />

      <Divider />

      <Metric
        label="Candles read"
        value={meta.candles_analyzed.toLocaleString()}
        help="Candles loaded from storage, including the extra ones read to satisfy both feature warmup and the largest requested target horizon."
      />
      <Metric
        label="Rows dropped (warmup)"
        value={meta.rows_dropped_warmup.toLocaleString()}
        help="Rows removed because at least one feature was not yet defined for them."
      />
      <Metric
        label="Rows dropped (horizon)"
        value={meta.rows_dropped_horizon.toLocaleString()}
        help="Trailing rows removed because at least one target has no future candle to compute it from yet — the core leakage-prevention trim. A training matrix must never contain an undefined label."
      />
      <Metric
        label="Largest horizon"
        value={`${meta.max_horizon} candle${meta.max_horizon === 1 ? '' : 's'}`}
      />
      <Metric label="Load time" value={`${meta.database_time_ms.toFixed(1)} ms`} />

      {meta.rows_dropped_horizon > 0 ? (
        <Alert severity="info" variant="outlined" sx={{ py: 0.5 }}>
          {meta.rows_dropped_horizon.toLocaleString()} trailing{' '}
          {meta.rows_dropped_horizon === 1 ? 'row was' : 'rows were'} dropped because no future
          candle exists yet to compute a target from.
        </Alert>
      ) : null}

      {quality.feature_failures.length > 0 ? (
        <Alert severity="warning" variant="outlined" sx={{ py: 0.5 }} role="alert">
          <Stack spacing={0.25}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {quality.feature_failures.length}{' '}
              {quality.feature_failures.length === 1 ? 'feature' : 'features'} failed to generate
            </Typography>
            {quality.feature_failures.map((failure) => (
              <Typography key={failure.feature} variant="caption">
                <strong>{failure.feature}</strong>: {failure.error_detail}
              </Typography>
            ))}
          </Stack>
        </Alert>
      ) : null}

      {targetFailures.length > 0 ? (
        <Alert severity="warning" variant="outlined" sx={{ py: 0.5 }} role="alert">
          <Stack spacing={0.25}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {targetFailures.length} {targetFailures.length === 1 ? 'target' : 'targets'} failed to
              generate
            </Typography>
            {targetFailures.map((failure) => (
              <Typography key={failure.target} variant="caption">
                <strong>{failure.target}</strong>: {failure.error_detail}
              </Typography>
            ))}
          </Stack>
        </Alert>
      ) : null}

      <Divider />

      <Typography variant="caption" color="text.secondary">
        Targets
      </Typography>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
        {targets.map((info) => (
          <Chip
            key={`${info.target}-${info.horizon}`}
            size="small"
            variant="outlined"
            label={`${info.label} v${info.version} (h=${info.horizon})`}
          />
        ))}
      </Stack>

      <Typography variant="caption" color="text.secondary">
        Builder v{meta.builder_version} · Target pipeline v{meta.target_pipeline_version} ·
        generated {meta.generated_at}
      </Typography>
    </Stack>
  );
}
