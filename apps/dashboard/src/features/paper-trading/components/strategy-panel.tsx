'use client';

import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useState } from 'react';
import type { PaperAccount } from '@/types/api/paper-trading';
import type { TrainingJobSummary } from '@/types/api/training';

export interface StrategyPanelProps {
  account: PaperAccount | undefined;
  isLoading: boolean;
  completedJobs: TrainingJobSummary[];
  submitting: boolean;
  submitError: string | null;
  onSave: (values: {
    enabled: boolean;
    trainingJobId: string | null;
    confidenceThresholdPct: string;
    defaultStopLossPct: string;
  }) => void;
}

/** `confidence_threshold_pct` is `(0, 100]` on the wire (`le=100`); `default_stop_loss_pct`
 * is `(0, 100)` (`lt=100` — a 100% stop-loss would mean a price of zero). */
function isValidPercent(value: string, { inclusiveMax }: { inclusiveMax: boolean }): boolean {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return false;
  return inclusiveMax ? parsed <= 100 : parsed < 100;
}

function jobLabel(job: TrainingJobSummary): string {
  return `${job.model_type} (${job.id.slice(0, 8)})`;
}

/**
 * Enable/disable this account's one automated strategy and tune its
 * confidence threshold / stop-loss — off by default, paper trading only,
 * and never able to open a position without a stop-loss (this field
 * accepts only `(0, 100)`, never a way to omit it entirely). Saving is
 * one explicit action, exactly like every other consequential change on
 * this page (`SetThresholdsDialog`, `CreateAccountDialog`) — no field
 * takes effect just by being typed into.
 *
 * The training job picker only ever offers *completed* jobs (the list
 * view doesn't carry a symbol to pre-filter on further) — a job never
 * trained on real market data still has nothing for the strategy to
 * predict from, so saving with one surfaces the backend's own rejection
 * as `submitError` rather than silently failing (see `ARCHITECTURE.md`
 * § "Automated Strategy").
 */
export function StrategyPanel({
  account,
  isLoading,
  completedJobs,
  submitting,
  submitError,
  onSave,
}: StrategyPanelProps) {
  const [enabled, setEnabled] = useState(false);
  const [trainingJobId, setTrainingJobId] = useState<string | null>(null);
  const [confidenceThresholdPct, setConfidenceThresholdPct] = useState('65');
  const [defaultStopLossPct, setDefaultStopLossPct] = useState('5');

  useEffect(() => {
    if (!account) return;
    setEnabled(account.strategy_enabled);
    setTrainingJobId(account.strategy_training_job_id);
    setConfidenceThresholdPct(account.strategy_confidence_threshold_pct);
    setDefaultStopLossPct(account.strategy_default_stop_loss_pct);
  }, [account]);

  if (isLoading || !account) {
    return (
      <Stack spacing={1}>
        <Skeleton variant="text" width={220} />
        <Skeleton variant="rectangular" height={40} />
      </Stack>
    );
  }

  const validThreshold = isValidPercent(confidenceThresholdPct, { inclusiveMax: true });
  const validStopLoss = isValidPercent(defaultStopLossPct, { inclusiveMax: false });
  const requiresJob = enabled && trainingJobId === null;
  const canSave = validThreshold && validStopLoss && !requiresJob;

  const selectedJob = completedJobs.find((job) => job.id === trainingJobId) ?? null;

  const handleSave = () => {
    if (!canSave) return;
    onSave({
      enabled,
      trainingJobId,
      confidenceThresholdPct,
      defaultStopLossPct,
    });
  };

  return (
    <Stack spacing={2}>
      <Alert severity="info">
        Paper trading only — this never places a real trade and never changes anything about how
        live trading is gated.
      </Alert>

      <FormControlLabel
        control={
          <Switch
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            slotProps={{ input: { 'aria-label': 'Enable automated strategy' } }}
          />
        }
        label={enabled ? 'Strategy enabled' : 'Strategy disabled'}
      />

      <Autocomplete
        size="small"
        options={completedJobs}
        value={selectedJob}
        getOptionLabel={jobLabel}
        isOptionEqualToValue={(option, value) => option.id === value.id}
        onChange={(_, next) => setTrainingJobId(next?.id ?? null)}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Training job"
            error={requiresJob}
            helperText={
              requiresJob
                ? 'Required while enabled — a completed job trained on real market data'
                : "The strategy always predicts for this job's own market"
            }
            slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Training job' } }}
          />
        )}
      />

      <TextField
        label="Confidence threshold (%)"
        value={confidenceThresholdPct}
        onChange={(event) => setConfidenceThresholdPct(event.target.value)}
        error={!validThreshold}
        helperText={
          validThreshold
            ? 'A fresh prediction must reach at least this confidence before the strategy acts'
            : 'Must be a number greater than 0 and no more than 100'
        }
        slotProps={{
          htmlInput: { 'aria-label': 'Confidence threshold percent', inputMode: 'decimal' },
        }}
      />

      <TextField
        label="Stop-loss (%)"
        value={defaultStopLossPct}
        onChange={(event) => setDefaultStopLossPct(event.target.value)}
        error={!validStopLoss}
        helperText={
          validStopLoss
            ? 'Every automated buy attaches a stop-loss this far below its own fill price — never optional'
            : 'Must be a number greater than 0 and less than 100'
        }
        slotProps={{
          htmlInput: { 'aria-label': 'Default stop-loss percent', inputMode: 'decimal' },
        }}
      />

      {submitError ? (
        <Alert severity="error" role="alert">
          {submitError}
        </Alert>
      ) : null}

      <Stack direction="row">
        <Button
          variant="contained"
          size="small"
          onClick={handleSave}
          disabled={!canSave || submitting}
        >
          {submitting ? 'Saving…' : 'Save'}
        </Button>
      </Stack>

      {!enabled ? (
        <Typography variant="caption" color="text.secondary">
          Off by default — turning this on requires an explicit save, and disabling takes effect
          before the scheduler&rsquo;s next cycle.
        </Typography>
      ) : null}
    </Stack>
  );
}
