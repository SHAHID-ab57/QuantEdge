'use client';

import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import type { ValidationReport } from '@/types/api/dataset-validation';

export interface ValidationStatisticsProps {
  report: ValidationReport;
}

function Field({ label, value, help }: { label: string; value: string; help?: string }) {
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
 * Run-level statistics: what was validated, and how long it took to check
 * it — the identity/provenance half of the report, complementing the
 * pass/fail verdict `ValidationSummaryCards` shows.
 */
export function ValidationStatistics({ report }: ValidationStatisticsProps) {
  return (
    <Stack spacing={1.25} aria-label="Validation statistics">
      <Field
        label="Dataset ID"
        value={report.dataset_id}
        help="Identifies the exact dataset build this report validated — a fresh id per build, not a content hash."
      />
      <Field label="Market" value={report.symbol} />
      <Field label="Timeframe" value={report.timeframe} />
      <Field label="Rows" value={report.rows.toLocaleString()} />
      <Field label="Columns" value={report.columns.toLocaleString()} />
      <Field
        label="Engine Version"
        value={report.engine_version}
        help="Version of the validation engine itself, independent of any single rule's own version."
      />
      <Field label="Validated" value={report.validated_at} />
      <Field label="Duration" value={`${report.duration_ms.toFixed(1)} ms`} />

      <Stack spacing={0.5}>
        <Typography variant="caption" color="text.secondary">
          Rules run ({report.rules_run.length})
        </Typography>
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {report.rules_run.map((rule) => (
            <Chip key={rule} size="small" variant="outlined" label={rule} />
          ))}
        </Stack>
      </Stack>
    </Stack>
  );
}
