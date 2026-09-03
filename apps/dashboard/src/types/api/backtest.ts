import { z } from 'zod';

/**
 * Wire schemas for the Backtesting Engine API (see
 * `services/api/app/api/v1/endpoints/backtest.py` /
 * `services/api/app/schemas/backtest.py`). Every response is validated
 * against these before the app trusts it, matching `prediction.ts`'s own
 * convention.
 */

export const BACKTEST_STATUSES = ['pending', 'running', 'completed', 'failed'] as const;

export const BacktestStatusSchema = z.enum(BACKTEST_STATUSES);

export type BacktestStatus = z.infer<typeof BacktestStatusSchema>;

export const BacktestRunSchema = z.object({
  id: z.string(),
  training_job_id: z.string(),
  experiment_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  step: z.string(),
  requested_start: z.string().datetime(),
  requested_end: z.string().datetime(),
  effective_end: z.string().datetime(),
  truncated: z.boolean(),
  status: BacktestStatusSchema,
  error_message: z.string().nullable(),
  started_at: z.string().datetime().nullable(),
  completed_at: z.string().datetime().nullable(),
  total_steps: z.number().int().nonnegative(),
  completed_steps: z.number().int().nonnegative(),
  graded_count: z.number().int().nonnegative(),
  model_kind: z.string(),
  aggregate_metrics: z.record(z.string(), z.number()).nullable(),
  created_at: z.string().datetime(),
});

export type BacktestRun = z.infer<typeof BacktestRunSchema>;

/** One row in Backtest History's list — metadata only, to keep the list light. */
export const BacktestSummarySchema = z.object({
  id: z.string(),
  training_job_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  step: z.string(),
  status: BacktestStatusSchema,
  truncated: z.boolean(),
  total_steps: z.number().int().nonnegative(),
  completed_steps: z.number().int().nonnegative(),
  graded_count: z.number().int().nonnegative(),
  created_at: z.string().datetime(),
  completed_at: z.string().datetime().nullable(),
});

export type BacktestSummary = z.infer<typeof BacktestSummarySchema>;

export const BacktestListResponseSchema = z.object({
  runs: z.array(BacktestSummarySchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export type BacktestListResponse = z.infer<typeof BacktestListResponseSchema>;
