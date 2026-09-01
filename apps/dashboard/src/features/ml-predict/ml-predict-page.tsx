'use client';

import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import { useState } from 'react';
import { Section } from '@/components/section';
import type { PredictionResponse, PredictionSummary } from '@/types/api/prediction';
import { PredictionForm } from './components/prediction-form';
import { PredictionHistoryTable } from './components/prediction-history-table';
import { PredictionResultPanel } from './components/prediction-result-panel';
import { usePrediction, usePredictionHistory, useRunPrediction } from './hooks/use-prediction-data';

const HISTORY_PAGE_SIZE = 10;

/**
 * The Live Prediction Service's page: given a completed training job and a
 * market, reconstruct a fresh feature vector, run the model, and show one
 * prediction — never as a bare number. The first usable output downstream
 * of a saved model artifact in this codebase; every earlier milestone
 * (data, features, datasets, experiments, training, evaluation) stops
 * there. Reopening a past prediction from Prediction History renders it
 * through the exact same `PredictionResultPanel` a fresh run does.
 */
export function MLPredictPage() {
  const [reopenedId, setReopenedId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);

  const run = useRunPrediction();
  const reopened = usePrediction(reopenedId);
  const history = usePredictionHistory({
    limit: HISTORY_PAGE_SIZE,
    offset: (historyPage - 1) * HISTORY_PAGE_SIZE,
  });

  const handleSubmit = (values: { trainingJobId: string; symbol: string; asOf: string | null }) => {
    setReopenedId(null);
    run.mutate({
      training_job_id: values.trainingJobId,
      symbol: values.symbol,
      ...(values.asOf ? { as_of: values.asOf } : {}),
    });
  };

  const handleReopen = (prediction: PredictionSummary) => {
    run.reset();
    setReopenedId(prediction.id);
  };

  const displayed: PredictionResponse | undefined = reopenedId ? reopened.data : run.data;

  return (
    <Stack spacing={2}>
      <Section
        title="Run a Live Prediction"
        subtitle="Reconstructs a fresh feature vector for a completed training job and predicts"
      >
        <Stack spacing={2}>
          <PredictionForm onSubmit={handleSubmit} submitting={run.isPending} />

          {run.isError ? (
            <Alert severity="error" role="alert">
              {run.error instanceof Error ? run.error.message : 'Could not run this prediction.'}
            </Alert>
          ) : null}

          {reopenedId && reopened.isError ? (
            <Alert severity="error" role="alert">
              {reopened.error instanceof Error
                ? reopened.error.message
                : 'Could not load this prediction.'}
            </Alert>
          ) : null}

          {displayed ? <PredictionResultPanel prediction={displayed} /> : null}
        </Stack>
      </Section>

      <Section
        title="Prediction History"
        subtitle="Every prediction you've run, most recent first — reopen to see it again"
      >
        <PredictionHistoryTable
          data={history.data}
          isLoading={history.isLoading}
          page={historyPage}
          limit={HISTORY_PAGE_SIZE}
          onPageChange={setHistoryPage}
          onReopen={handleReopen}
        />
      </Section>
    </Stack>
  );
}
