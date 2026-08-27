import { z } from 'zod';
import {
  DatasetFeatureInfoSchema,
  DatasetQualityReportSchema,
  FeatureColumnSchema,
} from './features';
import { ValidationReportSchema } from './dataset-validation';
import { IndicatorParameterSpecSchema } from './indicators';

/**
 * Wire schemas for the ML Dataset Builder API (see
 * `services/api/app/api/v1/endpoints/ml_datasets.py` /
 * `services/api/app/schemas/ml_datasets.py`). Every response is validated
 * against these before the app trusts it, matching the same convention as
 * `features.ts` and `dataset-validation.ts` — both of which are reused here
 * rather than redeclared, since a target-appended matrix is still a
 * `FeatureDataset` under the hood and the embedded validation verdict is
 * the exact same `ValidationReport` the Dataset Validation page renders.
 */

export const TargetDTOSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
  category: z.string(),
  parameters: z.array(IndicatorParameterSpecSchema),
  outputs: z.array(z.string()),
  version: z.string(),
  author: z.string(),
  value_type: z.string(),
  default_horizon: z.number().int().positive(),
  is_deterministic: z.boolean(),
});

export type TargetDTO = z.infer<typeof TargetDTOSchema>;

export const TargetCatalogResponseSchema = z.object({
  targets: z.array(TargetDTOSchema),
  total: z.number().int().nonnegative(),
  categories: z.array(z.string()),
});

export type TargetCatalogResponse = z.infer<typeof TargetCatalogResponseSchema>;

export const TargetFailureSchema = z.object({
  target: z.string(),
  params: z.record(z.string(), z.unknown()),
  error_code: z.string(),
  error_detail: z.string(),
});

export type TargetFailure = z.infer<typeof TargetFailureSchema>;

export const DatasetTargetInfoSchema = z.object({
  target: z.string(),
  label: z.string(),
  version: z.string(),
  parameters: z.record(z.string(), z.unknown()),
  columns: z.array(z.string()),
  horizon: z.number().int().nonnegative(),
  execution_time_ms: z.number(),
});

export type DatasetTargetInfo = z.infer<typeof DatasetTargetInfoSchema>;

export const SplitRatiosSchema = z.object({
  train: z.number(),
  validation: z.number(),
  test: z.number(),
});

export type SplitRatios = z.infer<typeof SplitRatiosSchema>;

export const SplitBoundsSchema = z.object({
  train_rows: z.number().int().nonnegative(),
  validation_rows: z.number().int().nonnegative(),
  test_rows: z.number().int().nonnegative(),
});

export type SplitBounds = z.infer<typeof SplitBoundsSchema>;

export const MLDatasetMetaSchema = z.object({
  row_count: z.number().int().nonnegative(),
  total_rows: z.number().int().nonnegative(),
  candles_analyzed: z.number().int().nonnegative(),
  rows_dropped_warmup: z.number().int().nonnegative(),
  rows_dropped_horizon: z.number().int().nonnegative(),
  warmup_candles: z.number().int().nonnegative(),
  max_horizon: z.number().int().nonnegative(),
  truncated: z.boolean(),
  database_time_ms: z.number(),
  pipeline_version: z.string(),
  target_pipeline_version: z.string(),
  builder_version: z.string(),
  generated_at: z.string().datetime(),
  created_at: z.string().datetime(),
});

export type MLDatasetMeta = z.infer<typeof MLDatasetMetaSchema>;

/**
 * A built, validated, split ML dataset. `split` is a per-row label parallel
 * to `rows`/`timestamps` (`"train" | "validation" | "test"`) rather than
 * three separate row arrays, matching the backend's single-flat-matrix
 * export shape exactly — a dataset is a view with a split column, not three
 * independent datasets.
 */
export const MLDatasetResponseSchema = z.object({
  ml_dataset_id: z.string(),
  dataset_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  columns: z.array(FeatureColumnSchema),
  feature_columns: z.array(z.string()),
  target_columns: z.array(z.string()),
  timestamps: z.array(z.string().datetime()),
  rows: z.array(z.array(z.union([z.number(), z.string(), z.boolean(), z.null()]))),
  split: z.array(z.enum(['train', 'validation', 'test'])),
  features: z.array(DatasetFeatureInfoSchema),
  targets: z.array(DatasetTargetInfoSchema),
  target_failures: z.array(TargetFailureSchema),
  split_ratios: SplitRatiosSchema,
  split_bounds: SplitBoundsSchema,
  quality: DatasetQualityReportSchema,
  validation: ValidationReportSchema,
  meta: MLDatasetMetaSchema,
});

export type MLDatasetResponse = z.infer<typeof MLDatasetResponseSchema>;

/**
 * Dataset History — every dataset `POST /markets/{symbol}/ml/dataset` has
 * built and persisted (see `services/api/app/models/ml_dataset_build.py`).
 * The list is metadata-only (`MLDatasetBuildSummarySchema`); reopening one
 * entry returns its full, untruncated `MLDatasetResponse` unchanged.
 */
export const MLDatasetBuildSummarySchema = z.object({
  id: z.string(),
  ml_dataset_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  row_count: z.number().int().nonnegative(),
  column_count: z.number().int().nonnegative(),
  feature_count: z.number().int().nonnegative(),
  target_count: z.number().int().nonnegative(),
  quality_passed: z.boolean(),
  created_at: z.string().datetime(),
});

export type MLDatasetBuildSummary = z.infer<typeof MLDatasetBuildSummarySchema>;

export const MLDatasetBuildListResponseSchema = z.object({
  builds: z.array(MLDatasetBuildSummarySchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export type MLDatasetBuildListResponse = z.infer<typeof MLDatasetBuildListResponseSchema>;

export const MLDatasetBuildDetailResponseSchema = z.object({
  id: z.string(),
  created_at: z.string().datetime(),
  dataset: MLDatasetResponseSchema,
});

export type MLDatasetBuildDetailResponse = z.infer<typeof MLDatasetBuildDetailResponseSchema>;
