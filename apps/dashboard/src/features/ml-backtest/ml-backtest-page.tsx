'use client';

import HistoryIcon from '@mui/icons-material/History';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import { useState } from 'react';
import { EmptyStateNotice } from '@/components/empty-state-notice';
import { Section } from '@/components/section';
import { PredictionHistoryTable } from '@/features/ml-predict/components/prediction-history-table';
import { usePredictionHistory } from '@/features/ml-predict/hooks/use-prediction-data';
import type { BacktestRun, BacktestSummary } from '@/types/api/backtest';
import { BacktestForm, type BacktestFormValues } from './components/backtest-form';
import { BacktestHistoryTable } from './components/backtest-history-table';
import { BacktestPredictionDetailDialog } from './components/backtest-prediction-detail-dialog';
import { BacktestResultPanel } from './components/backtest-result-panel';
import { useBacktest, useBacktestHistory, useRunBacktest } from './hooks/use-backtest-data';

const HISTORY_PAGE_SIZE = 10;
const DRILL_DOWN_PAGE_SIZE = 10;

/**
 * The Backtesting Engine's page: given a trained model and a historical
 * date range, walk it one step at a time — reusing the Live Prediction
 * Service and its grading logic completely unmodified, called in a loop
 * server-side (`app/services/backtest.py`) — and report aggregate
 * performance. Reopening a past run from Backtest History renders it
 * through the exact same `BacktestResultPanel` a fresh run does, and its
 * own predictions drill down through the *same* Prediction History table
 * the Live Prediction page uses, filtered to this run's `backtest_run_id`
 * so a backtest's many rows never flood the live view (see that table's
 * own default exclusion).
 */
export function MLBacktestPage() {
  const [reopenedId, setReopenedId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [drillDownPage, setDrillDownPage] = useState(1);
  const [reopenedPredictionId, setReopenedPredictionId] = useState<string | null>(null);

  const run = useRunBacktest();
  const reopened = useBacktest(reopenedId);
  const history = useBacktestHistory({
    limit: HISTORY_PAGE_SIZE,
    offset: (historyPage - 1) * HISTORY_PAGE_SIZE,
  });

  const displayed: BacktestRun | undefined = reopenedId ? reopened.data : run.data;

  const drillDown = usePredictionHistory(
    {
      backtest_run_id: displayed?.id,
      limit: DRILL_DOWN_PAGE_SIZE,
      offset: (drillDownPage - 1) * DRILL_DOWN_PAGE_SIZE,
    },
    { enabled: Boolean(displayed) },
  );

  const handleSubmit = (values: BacktestFormValues) => {
    setReopenedId(null);
    setDrillDownPage(1);
    run.mutate({
      training_job_id: values.trainingJobId,
      symbol: values.symbol,
      start: values.start,
      end: values.end,
      ...(values.step ? { step: values.step } : {}),
    });
  };

  const handleReopen = (summary: BacktestSummary) => {
    run.reset();
    setDrillDownPage(1);
    setReopenedId(summary.id);
  };

  return (
    <Stack spacing={2}>
      <Section
        title="Run a Backtest"
        subtitle="Walks a trained model over a historical date range, one live prediction and grade per step"
      >
        <Stack spacing={2}>
          <BacktestForm onSubmit={handleSubmit} submitting={run.isPending} />

          {run.isError ? (
            <Alert severity="error" role="alert">
              {run.error instanceof Error ? run.error.message : 'Could not start this backtest.'}
            </Alert>
          ) : null}

          {reopenedId && reopened.isError ? (
            <Alert severity="error" role="alert">
              {reopened.error instanceof Error
                ? reopened.error.message
                : 'Could not load this backtest run.'}
            </Alert>
          ) : null}

          {!displayed && !run.isError ? (
            <EmptyStateNotice
              icon={<HistoryIcon fontSize="small" color="disabled" />}
              title="No backtest run yet"
              description="Choose a training job, symbol, and date range above, then select Run Backtest."
            />
          ) : null}

          {displayed ? (
            <Stack spacing={2}>
              {reopenedId ? (
                <Alert severity="info" onClose={() => setReopenedId(null)}>
                  Viewing a reopened backtest from Backtest History.
                </Alert>
              ) : null}
              <BacktestResultPanel run={displayed} />
              <PredictionHistoryTable
                data={drillDown.data}
                isLoading={drillDown.isLoading}
                page={drillDownPage}
                limit={DRILL_DOWN_PAGE_SIZE}
                onPageChange={setDrillDownPage}
                onReopen={(prediction) => setReopenedPredictionId(prediction.id)}
              />
            </Stack>
          ) : null}
        </Stack>
      </Section>

      <Section
        title="Backtest History"
        subtitle="Every past backtest — reopen one to see its results again"
      >
        <BacktestHistoryTable
          data={history.data}
          isLoading={history.isLoading}
          page={historyPage}
          limit={HISTORY_PAGE_SIZE}
          onPageChange={setHistoryPage}
          onReopen={handleReopen}
        />
      </Section>

      <BacktestPredictionDetailDialog
        predictionId={reopenedPredictionId}
        onClose={() => setReopenedPredictionId(null)}
      />
    </Stack>
  );
}
