'use client';

import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import type { FeatureDataset } from '@/types/api/features';

/** "hit" tints green (a repeated identical request was served from the
 * Feature Cache without recomputing); "miss"/"disabled" stay neutral —
 * a miss is the normal, expected case for a first-time request, not a
 * problem to flag. */
function cacheChipColor(status: string | undefined): 'success' | 'default' {
  return status === 'hit' ? 'success' : 'default';
}

export interface DatasetSummaryProps {
  dataset: FeatureDataset;
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
      <Typography variant="body2" sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * The dataset's quality report: how trustworthy it is, and what was done
 * about it.
 *
 * The warmup notice is the important part. Dropped rows are the single
 * most confusing thing about a feature dataset — a researcher asks for 500
 * rows over a range and gets 451, with no obvious reason — so the count,
 * the cause, and the specific feature responsible are stated outright
 * rather than left to be inferred from a row count that looks wrong.
 *
 * Feature failures are surfaced the same way: the dataset builder's
 * partial-success contract (mirroring the indicator batch endpoint) means
 * one bad feature never blocks the others, but a researcher must still be
 * told which feature failed and why, not left to notice a missing column.
 *
 * Identity/reproducibility fields (dataset ID, pipeline version, market,
 * timeframe) live in `DatasetInfoCard` instead — this card is about
 * trustworthiness, that one is about identity.
 */
export function DatasetSummary({ dataset }: DatasetSummaryProps) {
  const { meta, quality } = dataset;
  const slowest = [...dataset.features].sort((a, b) => b.warmup - a.warmup)[0];
  const nullColumns = Object.entries(quality.null_counts).filter(([, count]) => count > 0);

  return (
    <Stack spacing={1.25} aria-label="Dataset summary">
      <Metric
        label="Candles read"
        value={meta.candles_analyzed.toLocaleString()}
        help="Candles loaded from storage, including the extra ones read only to satisfy warmup."
      />
      <Metric
        label="Rows dropped"
        value={meta.rows_dropped.toLocaleString()}
        help="Rows removed because at least one feature was not yet defined for them. A training matrix must not contain missing values."
      />
      <Metric
        label="Duplicate timestamps"
        value={quality.duplicate_timestamps.toLocaleString()}
        help="Candle timestamps appearing more than once in the loaded range. Expected to always be zero — the storage layer enforces uniqueness — so a nonzero count is a defensive signal worth investigating."
      />
      <Metric
        label="Missing candles"
        value={quality.missing_candles.toLocaleString()}
        help="Gaps in the loaded candle range at this timeframe's cadence — a hole in the source data, distinct from a warmup row this dataset deliberately drops."
      />
      <Metric label="Load time" value={`${meta.database_time_ms.toFixed(1)} ms`} />

      {meta.rows_dropped > 0 ? (
        <Alert severity="info" variant="outlined" sx={{ py: 0.5 }}>
          {meta.rows_dropped.toLocaleString()} warmup{' '}
          {meta.rows_dropped === 1 ? 'row was' : 'rows were'} dropped
          {slowest && slowest.warmup > 0
            ? ` — ${slowest.label} needs ${slowest.warmup} candles before its first value.`
            : '.'}
        </Alert>
      ) : null}

      {nullColumns.length > 0 ? (
        <Alert severity="info" variant="outlined" sx={{ py: 0.5 }}>
          Null values remain in {nullColumns.length === 1 ? 'column' : 'columns'}{' '}
          {nullColumns.map(([name]) => name).join(', ')} — expected for a feature whose
          `missing_values_expected` is set (e.g. an undefined ratio on a flat candle).
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

      <Divider />

      <Typography variant="caption" color="text.secondary">
        Features
      </Typography>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
        {dataset.features.map((info) => (
          <Tooltip
            key={info.feature}
            title={`${info.execution_time_ms.toFixed(2)} ms · cache ${info.cache_status ?? 'disabled'}`}
          >
            <Chip
              size="small"
              variant="outlined"
              color={cacheChipColor(info.cache_status)}
              label={`${info.label} v${info.version}`}
            />
          </Tooltip>
        ))}
      </Stack>

      <Typography variant="caption" color="text.secondary">
        Pipeline v{meta.pipeline_version} · generated {meta.generated_at}
      </Typography>
    </Stack>
  );
}
