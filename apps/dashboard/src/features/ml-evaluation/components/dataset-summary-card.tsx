'use client';

import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { BenchmarkCandidate } from '@/types/api/evaluation';

export interface DatasetSummaryCardProps {
  candidate: BenchmarkCandidate;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <Stack spacing={0.25} sx={{ minWidth: 120 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * Dataset Version, Symbol, Timeframe, Dataset Size, Feature Count, and
 * Target Column for one benchmark candidate — every value read straight off
 * the candidate the backend already returned (`symbol`/`timeframe` from the
 * training job itself; `feature_count`/`sample_count` from
 * `app/training/model_metadata.py`'s `collect_model_metadata`, already
 * computed at training time). Nothing here is recalculated.
 */
export function DatasetSummaryCard({ candidate }: DatasetSummaryCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase' }}>
          Dataset Summary
        </Typography>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <Field label="Dataset Version" value={candidate.dataset_version ?? '—'} />
          <Field label="Symbol" value={candidate.symbol ?? '—'} />
          <Field label="Timeframe" value={candidate.timeframe ?? '—'} />
          <Field
            label="Dataset Size"
            value={
              candidate.sample_count !== null && candidate.sample_count !== undefined
                ? `${candidate.sample_count.toLocaleString()} rows`
                : '—'
            }
          />
          <Field
            label="Feature Count"
            value={
              candidate.feature_count !== null && candidate.feature_count !== undefined
                ? String(candidate.feature_count)
                : '—'
            }
          />
          <Field label="Target Column" value={candidate.target_column ?? '—'} />
        </Stack>
      </Stack>
    </Paper>
  );
}
