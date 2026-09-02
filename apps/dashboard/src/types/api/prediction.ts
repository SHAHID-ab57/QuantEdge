import { z } from 'zod';

/**
 * Wire schemas for the Live Prediction Service API (see
 * `services/api/app/api/v1/endpoints/prediction.py` /
 * `services/api/app/schemas/prediction.py`). Every response is validated
 * against these before the app trusts it, matching `evaluation.ts`'s own
 * convention.
 */

/** A class label (classifier) or a number (regressor) — never anything else. */
export const PredictedValueSchema = z.union([z.string(), z.number(), z.boolean()]);

export type PredictedValue = z.infer<typeof PredictedValueSchema>;

export const PredictionResponseSchema = z.object({
  id: z.string(),
  training_job_id: z.string(),
  experiment_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  model_type: z.string(),
  model_kind: z.string(),
  target_column: z.string(),
  horizon: z.number().int().nullable(),
  as_of: z.string().datetime(),
  predicted_value: PredictedValueSchema,
  // `null` together whenever the model adapter has no `predict_proba` (every
  // regressor today) — `confidence_unavailable_reason` explains why in plain
  // language; never render a bare confidence without checking this first.
  confidence: z.number().nullable(),
  confidence_unavailable_reason: z.string().nullable(),
  probabilities: z.record(z.string(), z.number()).nullable(),
  classes: z.array(PredictedValueSchema).nullable(),
  feature_columns: z.array(z.string()),
  // `actual_outcome === null` is the one authoritative "still pending"
  // signal (never inferred from `is_correct`/`error`/`graded_at`) — see
  // `services/api/app/models/prediction.py`'s own docstring.
  actual_outcome: PredictedValueSchema.nullable(),
  // Classification only; null for a regressor (or while ungraded).
  is_correct: z.boolean().nullable(),
  // Regression only; null for a classifier (or while ungraded).
  error: z.number().nullable(),
  graded_at: z.string().datetime().nullable(),
  // Set only while ungraded: when grading can next determine the outcome.
  available_after: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
});

export type PredictionResponse = z.infer<typeof PredictionResponseSchema>;

/** One row in Prediction History's list — metadata only, to keep the list light. */
export const PredictionSummarySchema = z.object({
  id: z.string(),
  training_job_id: z.string(),
  experiment_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  model_type: z.string(),
  model_kind: z.string(),
  target_column: z.string(),
  horizon: z.number().int().nullable(),
  as_of: z.string().datetime(),
  predicted_value: PredictedValueSchema,
  confidence: z.number().nullable(),
  actual_outcome: PredictedValueSchema.nullable(),
  is_correct: z.boolean().nullable(),
  error: z.number().nullable(),
  graded_at: z.string().datetime().nullable(),
  available_after: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
});

export type PredictionSummary = z.infer<typeof PredictionSummarySchema>;

export const PredictionListResponseSchema = z.object({
  predictions: z.array(PredictionSummarySchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export type PredictionListResponse = z.infer<typeof PredictionListResponseSchema>;
