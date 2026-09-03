'use client';

import Alert from '@mui/material/Alert';
import Chip, { type ChipProps } from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { EvaluationSummary } from '@/features/ml-training/components/evaluation-summary';
import { toModelKind } from '@/features/ml-evaluation/lib/model-kind';
import type { BacktestRun, BacktestStatus } from '@/types/api/backtest';

const STATUS_COLORS: Record<BacktestStatus, ChipProps['color']> = {
  pending: 'default',
  running: 'info',
  completed: 'success',
  failed: 'error',
};

/**
 * One backtest run's own outcome: lifecycle status, honest truncation
 * reporting, step/grading progress, and — once complete — its aggregate
 * metrics. Reuses `EvaluationSummary` verbatim (the exact component
 * Benchmark History's own candidate detail already renders) rather than a
 * second metrics display — `summary={}` is deliberate: a backtest's own
 * `aggregate_metrics` is a flat `{name: value}` dict with none of a full
 * training job's confusion-matrix/feature-importance/prediction-sample
 * detail, and every one of `EvaluationSummary`'s own sub-sections already
 * renders nothing when its part of `summary` is absent.
 */
export function BacktestResultPanel({ run }: { run: BacktestRun }) {
  return (
    <Stack spacing={1.5} aria-label="Backtest result">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip size="small" color={STATUS_COLORS[run.status]} label={run.status} />
        <Typography variant="body2" color="text.secondary">
          {run.symbol} · {run.timeframe} · step {run.step}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {run.completed_steps}/{run.total_steps} steps · {run.graded_count} graded
        </Typography>
      </Stack>

      {run.truncated ? (
        <Alert severity="warning">
          The requested range needed more steps than this platform allows in one run — capped to{' '}
          {run.total_steps} steps, up to {new Date(run.effective_end).toLocaleString()}, rather than
          silently running a shorter backtest without saying so.
        </Alert>
      ) : null}

      {run.status === 'failed' ? (
        <Alert severity="error" role="alert">
          {run.error_message ?? 'This backtest failed.'}
        </Alert>
      ) : null}

      {run.status === 'completed' && run.aggregate_metrics ? (
        <EvaluationSummary
          modelKind={toModelKind(run.model_kind)}
          metrics={run.aggregate_metrics}
          summary={{}}
        />
      ) : null}
    </Stack>
  );
}
