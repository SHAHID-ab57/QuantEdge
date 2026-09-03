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

export interface BacktestFormValues {
  trainingJobId: string;
  symbol: string;
  start: string;
  end: string;
  step: string | null;
}

export interface BacktestFormProps {
  onSubmit: (values: BacktestFormValues) => void;
  submitting: boolean;
}

/**
 * Training job, symbol, date range, and an optional step — the same
 * searchable-combobox job/symbol selection `PredictionForm` already uses,
 * filtered to completed jobs (the only ones with a saved model artifact to
 * walk). A job that completed without training on real data (e.g.
 * `placeholder`) still appears here and is rejected with a clear, explained
 * error only once submitted, the same "let the request explain it" posture
 * `PredictionForm` already takes for the identical condition.
 */
export function BacktestForm({ onSubmit, submitting }: BacktestFormProps) {
  const [trainingJob, setTrainingJob] = useState<TrainingJobSummary | null>(null);
  const [symbol, setSymbol] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [step, setStep] = useState('');

  const jobs = useQuery({
    queryKey: ['training-jobs', 'select-options', 'completed'],
    queryFn: () =>
      fetchTrainingJobs({ status: 'completed', limit: 200, sort: 'updated_at', dir: 'desc' }),
  });
  const marketsData = useMarkets();

  const jobOptions = useMemo(() => jobs.data?.jobs ?? EMPTY_JOBS, [jobs.data]);

  const canSubmit = Boolean(trainingJob && symbol && start && end) && !submitting;

  const handleSubmit = () => {
    if (!trainingJob || !symbol || !start || !end) return;
    onSubmit({
      trainingJobId: trainingJob.id,
      symbol,
      start: new Date(start).toISOString(),
      end: new Date(end).toISOString(),
      step: step.trim() || null,
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
              body: 'The completed training job whose saved model this backtest walks — the exact same model a live prediction would use.',
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
              helperText="The market to walk."
              slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Symbol' } }}
            />
          )}
        />
        <InfoTooltip
          label="Symbol"
          sections={[
            {
              heading: 'What it is',
              body: 'Which market this backtest walks, using the training job’s own recorded feature_set.',
            },
          ]}
        />
      </Stack>

      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <TextField
          type="datetime-local"
          label="Start"
          required
          value={start}
          onChange={(event) => setStart(event.target.value)}
          helperText="First as_of to predict at."
          sx={{ flex: 1, minWidth: 220 }}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'Start' } }}
        />
        <TextField
          type="datetime-local"
          label="End"
          required
          value={end}
          onChange={(event) => setEnd(event.target.value)}
          helperText="Walk stops before this instant."
          sx={{ flex: 1, minWidth: 220 }}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'End' } }}
        />
      </Stack>

      <Stack direction="row" spacing={0.5} alignItems="flex-start">
        <TextField
          fullWidth
          label="Step"
          value={step}
          onChange={(event) => setStep(event.target.value)}
          helperText="Optional — defaults to the training job's own timeframe (e.g. 1h)."
          slotProps={{ htmlInput: { 'aria-label': 'Step' } }}
        />
        <InfoTooltip
          label="Step"
          sections={[
            { heading: 'What it is', body: 'The walk’s own step timeframe, e.g. 1h.' },
            {
              heading: 'Constraint',
              body: 'Must be the same as, or coarser than, the training job’s own timeframe — a step finer than the model’s own candle resolution would just re-predict the same row.',
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
        {submitting ? 'Starting…' : 'Run Backtest'}
      </Button>
    </Stack>
  );
}
