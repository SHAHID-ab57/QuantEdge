'use client';

import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { InfoTooltip } from '@/components/info-tooltip';
import { useMarkets } from '@/features/history/hooks/use-history-data';
import { fetchTrainingJobs } from '@/lib/api/training';
import type { TrainingJobSummary } from '@/types/api/training';

const EMPTY_JOBS: TrainingJobSummary[] = [];

export interface PredictionFormProps {
  onSubmit: (values: { trainingJobId: string; symbol: string; asOf: string | null }) => void;
  submitting: boolean;
}

/**
 * Training job selection, symbol, and an optional as-of timestamp — the
 * same searchable-combobox experiment/job selection pattern
 * `CreateTrainingJobDialog` already uses, filtered here to completed jobs
 * (the only ones with a saved model artifact to predict with).
 *
 * `GET /training-jobs`'s own list shape doesn't record whether a job has a
 * saved artifact (only its detail's `result_summary` does) — filtering by
 * `status=completed` is as far as this can narrow it client-side; a job
 * that completed without training on real data (e.g. `placeholder`) still
 * appears here and is rejected with a clear, explained error only once
 * selected and actually run, the same "let the request explain it" posture
 * this platform's other forms already take for a condition their own list
 * endpoint can't pre-filter.
 */
export function PredictionForm({ onSubmit, submitting }: PredictionFormProps) {
  const [trainingJob, setTrainingJob] = useState<TrainingJobSummary | null>(null);
  const [symbol, setSymbol] = useState('');
  const [asOf, setAsOf] = useState('');

  const jobs = useQuery({
    queryKey: ['training-jobs', 'select-options', 'completed'],
    queryFn: () =>
      fetchTrainingJobs({ status: 'completed', limit: 200, sort: 'updated_at', dir: 'desc' }),
  });
  const marketsData = useMarkets();

  const jobOptions = useMemo(() => jobs.data?.jobs ?? EMPTY_JOBS, [jobs.data]);

  const canSubmit = Boolean(trainingJob && symbol) && !submitting;

  const handleSubmit = () => {
    if (!trainingJob || !symbol) return;
    onSubmit({
      trainingJobId: trainingJob.id,
      symbol,
      asOf: asOf ? new Date(asOf).toISOString() : null,
    });
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={0.5} alignItems="flex-start">
        <Autocomplete
          fullWidth
          options={jobOptions}
          value={trainingJob}
          loading={jobs.isLoading}
          getOptionLabel={(option) => `${option.model_type} · ${option.id.slice(0, 8)}`}
          isOptionEqualToValue={(option, value) => option.id === value.id}
          onChange={(_, next) => setTrainingJob(next)}
          noOptionsText="No completed training jobs match your search"
          renderInput={(params) => (
            <TextField
              {...params}
              label="Training job"
              required
              helperText={
                jobs.isLoading
                  ? 'Loading completed training jobs…'
                  : 'A completed job with a saved model artifact.'
              }
              slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Training job' } }}
            />
          )}
        />
        <InfoTooltip
          label="Training job"
          sections={[
            {
              heading: 'What it is',
              body: 'The completed training job whose saved model this prediction runs.',
            },
            {
              heading: 'Why only completed jobs',
              body: 'Only a completed job has a serialized model artifact to load — a pending, running, failed, or cancelled job has nothing to predict with.',
            },
          ]}
        />
      </Stack>

      <Stack direction="row" spacing={0.5} alignItems="flex-start">
        <Autocomplete
          fullWidth
          options={marketsData.data?.markets ?? []}
          loading={marketsData.isLoading}
          value={marketsData.data?.markets.find((m) => m.symbol === symbol) ?? null}
          getOptionLabel={(option) => option.symbol}
          isOptionEqualToValue={(option, value) => option.symbol === value.symbol}
          onChange={(_, next) => setSymbol(next?.symbol ?? '')}
          noOptionsText="No markets match your search"
          renderInput={(params) => (
            <TextField
              {...params}
              label="Symbol"
              required
              helperText="The market to compute a fresh feature vector for."
              slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Symbol' } }}
            />
          )}
        />
        <InfoTooltip
          label="Symbol"
          sections={[
            {
              heading: 'What it is',
              body: 'Which market a fresh feature vector is computed for, using the training job’s own recorded feature_set.',
            },
          ]}
        />
      </Stack>

      <Stack direction="row" spacing={0.5} alignItems="flex-start">
        <TextField
          fullWidth
          type="datetime-local"
          label="As of"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          helperText="Optional — defaults to the latest available candle."
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'As of' } }}
        />
        <InfoTooltip
          label="As of"
          sections={[
            {
              heading: 'What it is',
              body: 'Predict as of this candle timestamp instead of the latest one.',
            },
            {
              heading: 'How it resolves',
              body: 'The feature vector is computed from the real stored candle at or before this instant — never an interpolated one, and the response’s own as_of always reports which candle was actually used.',
            },
          ]}
        />
      </Stack>

      {!jobs.isLoading && jobOptions.length === 0 ? (
        <Alert severity="info" role="status">
          No completed training jobs yet — train and run one on the ML Training page first.
        </Alert>
      ) : null}

      <Button variant="contained" onClick={handleSubmit} disabled={!canSubmit}>
        {submitting ? 'Predicting…' : 'Run Prediction'}
      </Button>
    </Stack>
  );
}
