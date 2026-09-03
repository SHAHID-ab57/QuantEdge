import { apiClient } from './client';
import {
  BacktestListResponseSchema,
  BacktestRunSchema,
  type BacktestListResponse,
  type BacktestRun,
  type BacktestStatus,
} from '@/types/api/backtest';

export interface BacktestRunBody {
  training_job_id: string;
  symbol: string;
  /** ISO-8601. */
  start: string;
  /** ISO-8601. */
  end: string;
  /** Defaults to the training job's own timeframe. */
  step?: string;
}

/** Plan and start a backtest — returns once the run is persisted and moved to
 * 'running', well before the walk itself finishes (see that endpoint's own
 * description). */
export async function runBacktest(body: BacktestRunBody): Promise<BacktestRun> {
  const { data } = await apiClient.post('/api/v1/backtests/run', body);
  return BacktestRunSchema.parse(data);
}

/** Reopen one past backtest run — its exact request and (once settled) outcome. */
export async function fetchBacktest(id: string): Promise<BacktestRun> {
  const { data } = await apiClient.get(`/api/v1/backtests/${encodeURIComponent(id)}`);
  return BacktestRunSchema.parse(data);
}

export interface BacktestListParams {
  training_job_id?: string;
  experiment_id?: string;
  symbol?: string;
  status?: BacktestStatus;
  sort?: 'symbol' | 'status' | 'created_at' | 'started_at' | 'completed_at';
  dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

/** Backtest History's list view — every past run this platform has recorded. */
export async function fetchBacktests(
  params: BacktestListParams = {},
): Promise<BacktestListResponse> {
  const { data } = await apiClient.get('/api/v1/backtests', { params });
  return BacktestListResponseSchema.parse(data);
}
