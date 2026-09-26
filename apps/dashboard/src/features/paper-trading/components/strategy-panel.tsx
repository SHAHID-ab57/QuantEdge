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
    leverage: string;
  }) => void;
}

/** `confidence_threshold_pct` is `(0, 100]` on the wire (`le=100`); `default_stop_loss_pct`
 * is `(0, 100)` (`lt=100` — a 100% stop-loss would mean a price of zero). */
function isValidPercent(value: string, { inclusiveMax }: { inclusiveMax: boolean }): boolean {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return false;
  return inclusiveMax ? parsed <= 100 : parsed < 100;
}

/** Leverage is `[1, max_leverage]`: never below 1x, never above the account's own ceiling. */
function isValidLeverage(value: string, maxLeverage: number): boolean {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 1 && parsed <= maxLeverage;
}

function jobLabel(job: TrainingJobSummary): string {
  return `${job.model_type} (${job.id.slice(0, 8)})`;
}

/**
 * Enable/disable this account's one automated strategy and tune its
 * confidence threshold / stop-loss / leverage — off by default, paper trading
 * only, and never able to open a position without a stop-loss (this field
 * accepts only `(0, 100)`, never a way to omit it entirely). The strategy
 * trades both directions from the model's call (up = long, down = short) at
 * ONE fixed leverage. That leverage is deliberately a plain number set here,
 * never scaled by the prediction's confidence, which has been measured to
 * carry no reliable relationship to being right. Saving is
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
 *
 * `account.strategy_paused_reason === 'feature_drift'` renders a distinct
 * error banner above the enable switch — the scheduler's own auto-pause
 * (FEATURE-DRIFT-MONITOR, `ARCHITECTURE.md` § "Feature Drift Monitoring")
 * left `strategy_enabled` false the same way a human's own disable would,
 * and without this the two are indistinguishable from the outside. Saving
 * with the switch on again is what clears it — no separate "acknowledge"
 * action exists.
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
  const [leverage, setLeverage] = useState('2');

  useEffect(() => {
    if (!account) return;
    setEnabled(account.strategy_enabled);
    setTrainingJobId(account.strategy_training_job_id);
    setConfidenceThresholdPct(account.strategy_confidence_threshold_pct);
    setDefaultStopLossPct(account.strategy_default_stop_loss_pct);
    setLeverage(account.strategy_leverage);
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
  const maxLeverage = Number(account.max_leverage);
  const validLeverage = isValidLeverage(leverage, maxLeverage);
  const requiresJob = enabled && trainingJobId === null;
  const canSave = validThreshold && validStopLoss && validLeverage && !requiresJob;

  const selectedJob = completedJobs.find((job) => job.id === trainingJobId) ?? null;

  const handleSave = () => {
    if (!canSave) return;
    onSave({
      enabled,
      trainingJobId,
      confidenceThresholdPct,
      defaultStopLossPct,
      leverage,
    });
  };

  return (
    <Stack spacing={2}>
      <Alert severity="info">
        Paper trading only — this never places a real trade and never changes anything about how
        live trading is gated.
      </Alert>
      <Alert severity="warning">
        This strategy trades <strong>both directions</strong>: a confident &ldquo;up&rdquo; call
        opens a long, a confident &ldquo;down&rdquo; call opens a short. The live model has called
        &ldquo;down&rdquo; in over 99% of cases across every regime tested, so expect it to be short
        almost all the time. That is the model&rsquo;s own measured behavior, visible in the
        decision log below, not a bug.
      </Alert>

      {account.strategy_paused_reason === 'feature_drift' ? (
        <Alert severity="error" role="alert">
          <strong>Automated strategy auto-paused — feature drift detected.</strong> A fresh
          prediction&rsquo;s own input was an extreme outlier against this job&rsquo;s training data
          (see the decision log below for which feature and by how much), so the strategy was
          disabled before it could act on it
          {account.strategy_paused_at
            ? ` at ${new Date(account.strategy_paused_at).toLocaleString()}`
            : ''}
          . This does not clear itself — review the training job (it likely needs retraining on more
          recent data) before turning the switch back on below.
        </Alert>
      ) : null}

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
            ? 'Every automated entry attaches a stop-loss this far on the losing side of its fill price (below a long, above a short) — never optional'
            : 'Must be a number greater than 0 and less than 100'
        }
        slotProps={{
          htmlInput: { 'aria-label': 'Default stop-loss percent', inputMode: 'decimal' },
        }}
      />

      <TextField
        label="Leverage (x)"
        value={leverage}
        onChange={(event) => setLeverage(event.target.value)}
        error={!validLeverage}
        helperText={
          validLeverage
            ? `One fixed leverage for every automated entry, long or short — never derived from the prediction's confidence. This account allows up to ${maxLeverage}x; the stop-loss must sit inside the liquidation distance.`
            : `Must be a number from 1 to ${maxLeverage} (this account's maximum)`
        }
        slotProps={{
          htmlInput: { 'aria-label': 'Strategy leverage', inputMode: 'decimal' },
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
