'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchBacktest,
  fetchBacktests,
  runBacktest,
  type BacktestListParams,
  type BacktestRunBody,
} from '@/lib/api/backtest';

/** Server state for the Backtesting Engine page — starting a run is a
 * *mutation* (an explicit, on-demand walk over historical data, never
 * something that should silently re-run on remount, the same posture
 * `useRunTrainingJob`/`useRunPrediction` already take); Backtest History
 * and one run's own detail (a real persisted, listable/reopenable
 * resource) are queries. */

const BACKTEST_HISTORY_KEY = ['backtests'] as const;

export function useRunBacktest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BacktestRunBody) => runBacktest(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: BACKTEST_HISTORY_KEY }),
  });
}

export function useBacktestHistory(params: BacktestListParams) {
  return useQuery({
    queryKey: [...BACKTEST_HISTORY_KEY, 'list', params],
    queryFn: () => fetchBacktests(params),
  });
}

/**
 * Polls every 3s while the run is still 'running' — the walk itself
 * executes in a background task server-side (`POST /backtests/run` returns
 * once the run is planned and started, well before it finishes), so this
 * poll is what actually shows progress from there, the same pattern
 * `useTrainingJob` already established for training jobs.
 */
export function useBacktest(id: string | null) {
  return useQuery({
    queryKey: [...BACKTEST_HISTORY_KEY, 'detail', id],
    queryFn: () => fetchBacktest(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  });
}
