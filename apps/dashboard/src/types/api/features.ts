import { z } from 'zod';
import { IndicatorParameterSpecSchema } from './indicators';

/**
 * Wire schemas for the feature engineering API (see
 * `services/api/app/api/v1/endpoints/features.py`). Every response is
 * validated against these before the app trusts it, matching the same
 * convention as `market.ts` and `indicators.ts`.
 *
 * `IndicatorParameterSpecSchema` is reused rather than redeclared: the
 * backend publishes feature parameters using the *same* `ParameterSpec`
 * type it publishes indicator parameters with, so a second schema here
 * would be a copy guaranteed to drift.
 */

export const FeatureSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
  category: z.string(),
  parameters: z.array(IndicatorParameterSpecSchema),
  /** Column-name templates this generator produces, e.g. `sma_{period}`. */
  outputs: z.array(z.string()),
  /** Generator-level semver; a change means previously-built datasets differ. */
  version: z.string(),
  author: z.string(),
  complexity: z.string(),
  warmup_description: z.string(),
  aliases: z.array(z.string()).optional(),
  /** Free-form unit of the produced values, e.g. "price" or "ratio". */
  unit: z.string().optional(),
  /** Predominant column dtype: "float" | "int" | "bool" | "categorical" | "mixed". */
  value_type: z.string().optional(),
  /** Other registered features this one depends on (an AI-readiness extension point). */
  dependencies: z.array(z.string()).optional(),
  /** Whether identical candles and parameters always produce identical output. */
  is_deterministic: z.boolean().optional(),
  /** Whether this generator can produce nulls beyond its declared warmup. */
  missing_values_expected: z.boolean().optional(),
});

export type Feature = z.infer<typeof FeatureSchema>;

export const FeatureCatalogSchema = z.object({
  features: z.array(FeatureSchema),
  total: z.number().int().nonnegative(),
  categories: z.array(z.string()),
});

export type FeatureCatalog = z.infer<typeof FeatureCatalogSchema>;

export const FeatureColumnSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
  /** How a consumer should encode this column: a categorical is not scaled. */
  dtype: z.string(),
});

export type FeatureColumn = z.infer<typeof FeatureColumnSchema>;

/** How one requested feature resolved — the dataset's provenance record. */
export const DatasetFeatureInfoSchema = z.object({
  feature: z.string(),
  label: z.string(),
  version: z.string(),
  /** Fully resolved, defaults applied — the values that actually ran. */
  parameters: z.record(z.string(), z.unknown()),
  columns: z.array(z.string()),
  warmup: z.number().int().nonnegative(),
  execution_time_ms: z.number(),
  /** "hit" | "miss" | "disabled" — see the Feature Cache. */
  cache_status: z.string().optional(),
});

export type DatasetFeatureInfo = z.infer<typeof DatasetFeatureInfoSchema>;

export const FeatureDatasetMetaSchema = z.object({
  row_count: z.number().int().nonnegative(),
  /** Rows in the full dataset — differs from `row_count` when previewing. */
  total_rows: z.number().int().nonnegative(),
  candles_analyzed: z.number().int().nonnegative(),
  rows_dropped: z.number().int().nonnegative(),
  warmup_candles: z.number().int().nonnegative(),
  truncated: z.boolean(),
  database_time_ms: z.number(),
  pipeline_version: z.string(),
  generated_at: z.string().datetime(),
});

export type FeatureDatasetMeta = z.infer<typeof FeatureDatasetMetaSchema>;

/** One requested feature that could not be generated, and why. */
export const FeatureFailureSchema = z.object({
  feature: z.string(),
  params: z.record(z.string(), z.unknown()),
  error_code: z.string(),
  error_detail: z.string(),
});

export type FeatureFailure = z.infer<typeof FeatureFailureSchema>;

/**
 * How trustworthy a built dataset is, and what was done about it — see
 * `ARCHITECTURE.md` § "Feature Engineering Engine" for the full rationale
 * behind each field.
 */
export const DatasetQualityReportSchema = z.object({
  total_rows: z.number().int().nonnegative(),
  rows_returned: z.number().int().nonnegative(),
  rows_removed: z.number().int().nonnegative(),
  /** Null count per column, before warmup trimming. */
  null_counts: z.record(z.string(), z.number().int().nonnegative()),
  duplicate_timestamps: z.number().int().nonnegative(),
  missing_candles: z.number().int().nonnegative(),
  feature_failures: z.array(FeatureFailureSchema),
  generation_time_ms: z.number(),
});

export type DatasetQualityReport = z.infer<typeof DatasetQualityReportSchema>;

/**
 * A built dataset. `rows` is row-oriented and parallel to `timestamps`,
 * with each row's values ordered exactly as `columns` — the shape a preview
 * table renders directly.
 */
export const FeatureDatasetSchema = z.object({
  /** Unique per build — identifies this exact dataset snapshot. */
  dataset_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  columns: z.array(FeatureColumnSchema),
  timestamps: z.array(z.string().datetime()),
  rows: z.array(z.array(z.union([z.number(), z.string(), z.boolean(), z.null()]))),
  features: z.array(DatasetFeatureInfoSchema),
  meta: FeatureDatasetMetaSchema,
  quality: DatasetQualityReportSchema,
});

export type FeatureDataset = z.infer<typeof FeatureDatasetSchema>;

/** One cell of a dataset row. */
export type FeatureCell = FeatureDataset['rows'][number][number];

/** Pairwise Pearson correlation across a built dataset's numeric columns. */
export const FeatureCorrelationSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  columns: z.array(z.string()),
  matrix: z.array(z.array(z.number())),
  row_count: z.number().int().nonnegative(),
});

export type FeatureCorrelation = z.infer<typeof FeatureCorrelationSchema>;

/** Summary statistics for one column over a full (non-preview-capped) dataset. */
export const ColumnStatisticsSchema = z.object({
  column: z.string(),
  count: z.number().int().nonnegative(),
  null_count: z.number().int().nonnegative(),
  mean: z.number().nullable(),
  std: z.number().nullable(),
  minimum: z.number().nullable(),
  maximum: z.number().nullable(),
});

export type ColumnStatistics = z.infer<typeof ColumnStatisticsSchema>;

export const FeatureStatisticsSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  columns: z.array(ColumnStatisticsSchema),
  row_count: z.number().int().nonnegative(),
});

export type FeatureStatistics = z.infer<typeof FeatureStatisticsSchema>;

/** One feature's place in the whole registry's dependency graph. */
export const FeatureLineageNodeSchema = z.object({
  name: z.string(),
  label: z.string(),
  category: z.string(),
  dependencies: z.array(z.string()),
  depended_on_by: z.array(z.string()),
  ancestors: z.array(z.string()),
  descendants: z.array(z.string()),
});

export type FeatureLineageNode = z.infer<typeof FeatureLineageNodeSchema>;

export const FeatureLineageSchema = z.object({
  nodes: z.array(FeatureLineageNodeSchema),
  edges: z.array(z.tuple([z.string(), z.string()])),
  topological_order: z.array(z.string()),
});

export type FeatureLineage = z.infer<typeof FeatureLineageSchema>;
