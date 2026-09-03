'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchPrediction,
  fetchPredictions,
  runPrediction,
  type PredictionListParams,
  type PredictionRunBody,
} from '@/lib/api/prediction';

/** Server state for the Live Prediction Service page. Running a prediction is a
 * *mutation*, not a query — an explicit, on-demand action over real, freshly
 * loaded candles, never something that should silently re-run on remount, the
 * same "explicit action" posture `useBuildDataset`/`useBenchmark` already take
 * for their own real, potentially expensive backend computations. Prediction
 * History (a real persisted, listable/reopenable resource) is a query. */

const PREDICTION_HISTORY_KEY = ['predictions'] as const;

export function useRunPrediction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PredictionRunBody) => runPrediction(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PREDICTION_HISTORY_KEY }),
  });
}

/**
 * `options.enabled` (default `true`) lets a caller that filters by
 * `backtest_run_id` — the Backtesting Engine's own drill-down, reusing this
 * hook verbatim rather than a second one — skip the request entirely until
 * a run actually exists to filter by, instead of firing a request for the
 * default (live-only) view every time.
 */
export function usePredictionHistory(
  params: PredictionListParams,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [...PREDICTION_HISTORY_KEY, 'list', params],
    queryFn: () => fetchPredictions(params),
    enabled: options.enabled ?? true,
  });
}

export function usePrediction(id: string | null) {
  return useQuery({
    queryKey: [...PREDICTION_HISTORY_KEY, 'detail', id],
    queryFn: () => fetchPrediction(id as string),
    enabled: Boolean(id),
  });
}
