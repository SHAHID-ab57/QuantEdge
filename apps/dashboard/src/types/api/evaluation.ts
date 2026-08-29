import { z } from 'zod';

/**
 * Wire schemas for the Model Evaluation & Benchmarking Engine API (see
 * `services/api/app/api/v1/endpoints/evaluation.py` /
 * `services/api/app/schemas/evaluation.py`). Every response is validated
 * against these before the app trusts it, matching `training.ts`'s own
 * convention.
 */

export const MetricCategorySchema = z.enum(['classification', 'regression']);

export type MetricCategory = z.infer<typeof MetricCategorySchema>;

export const MetricMetadataSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
  category: MetricCategorySchema,
  higher_is_better: z.boolean(),
  requires_probabilities: z.boolean(),
  version: z.string(),
});

export type MetricMetadata = z.infer<typeof MetricMetadataSchema>;

export const MetricCatalogResponseSchema = z.object({
  metrics: z.array(MetricMetadataSchema),
});

export type MetricCatalogResponse = z.infer<typeof MetricCatalogResponseSchema>;

export const BenchmarkCandidateSchema = z.object({
  training_job_id: z.string(),
  experiment_id: z.string(),
  experiment_name: z.string(),
  model_type: z.string(),
  model_kind: z.string(),
  dataset_version: z.string().nullable(),
  target_column: z.string().nullable(),
  completed_at: z.string().datetime().nullable(),
  metrics: z.record(z.string(), z.number()),
  // Dataset Summary Card + deep-link fields — all reused from data the
  // training run itself already produced (`app/training/model_metadata.py`,
  // `ModelSerializer.save`), never recomputed by this engine.
  symbol: z.string().nullable().optional(),
  timeframe: z.string().nullable().optional(),
  feature_count: z.number().int().nullable().optional(),
  sample_count: z.number().int().nullable().optional(),
  model_artifact_url: z.string().nullable().optional(),
  // The job's own `result_summary`, verbatim — lets the frontend reuse its
  // existing `EvaluationSummary` component (confusion matrix, ROC/PR
  // curves, feature importance, prediction samples) for one candidate's
  // full detail, with nothing recomputed on either side.
  report: z.record(z.string(), z.unknown()).optional(),
});

export type BenchmarkCandidate = z.infer<typeof BenchmarkCandidateSchema>;

export const BenchmarkBestEntrySchema = z.object({
  metric: z.string(),
  training_job_id: z.string(),
  model_type: z.string(),
  value: z.number(),
  higher_is_better: z.boolean(),
});

export type BenchmarkBestEntry = z.infer<typeof BenchmarkBestEntrySchema>;

export const BenchmarkResponseSchema = z.object({
  candidates: z.array(BenchmarkCandidateSchema),
  best_by_metric: z.array(BenchmarkBestEntrySchema),
});

export type BenchmarkResponse = z.infer<typeof BenchmarkResponseSchema>;

/** Echoes `BenchmarkRequest` back inside a reopened Benchmark History run. */
export const BenchmarkRequestEchoSchema = z.object({
  dataset_version: z.string().nullable().optional(),
  target_column: z.string().nullable().optional(),
  experiment_ids: z.array(z.string()).optional(),
});

export type BenchmarkRequestEcho = z.infer<typeof BenchmarkRequestEchoSchema>;

export const BenchmarkRunSummarySchema = z.object({
  id: z.string(),
  dataset_version: z.string().nullable(),
  target_column: z.string().nullable(),
  candidate_count: z.number().int(),
  created_at: z.string().datetime(),
});

export type BenchmarkRunSummary = z.infer<typeof BenchmarkRunSummarySchema>;

export const BenchmarkRunListResponseSchema = z.object({
  runs: z.array(BenchmarkRunSummarySchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});

export type BenchmarkRunListResponse = z.infer<typeof BenchmarkRunListResponseSchema>;

export const BenchmarkRunDetailResponseSchema = z.object({
  id: z.string(),
  created_at: z.string().datetime(),
  request: BenchmarkRequestEchoSchema,
  response: BenchmarkResponseSchema,
});

export type BenchmarkRunDetailResponse = z.infer<typeof BenchmarkRunDetailResponseSchema>;
