import { z } from 'zod';

/**
 * Wire schemas for the Experiment Management API (see
 * `services/api/app/api/v1/endpoints/experiments.py` /
 * `services/api/app/schemas/experiments.py`). Every response is validated
 * against these before the app trusts it, matching the same convention as
 * `features.ts`, `dataset-validation.ts`, and `ml-datasets.ts`.
 */

export const EXPERIMENT_STATUSES = ['draft', 'running', 'completed', 'failed', 'archived'] as const;

export const ExperimentStatusSchema = z.enum(EXPERIMENT_STATUSES);

export type ExperimentStatus = z.infer<typeof ExperimentStatusSchema>;

export const ARTIFACT_TYPES = [
  'dataset_export',
  'model_checkpoint',
  'report',
  'plot',
  'other',
] as const;

export const ArtifactTypeSchema = z.enum(ARTIFACT_TYPES);

export type ArtifactType = z.infer<typeof ArtifactTypeSchema>;

export const FeatureRequestSchema = z.object({
  feature: z.string(),
  params: z.record(z.string(), z.string()).default({}),
});

export type FeatureRequest = z.infer<typeof FeatureRequestSchema>;

export const TargetRequestSchema = z.object({
  target: z.string(),
  params: z.record(z.string(), z.string()).default({}),
});

export type TargetRequest = z.infer<typeof TargetRequestSchema>;

export const SplitConfigSchema = z.object({
  train: z.number().min(0).max(1),
  validation: z.number().min(0).max(1),
  test: z.number().min(0).max(1),
});

export type SplitConfig = z.infer<typeof SplitConfigSchema>;

export const MetricSchema = z.object({
  id: z.string(),
  name: z.string(),
  value: z.number(),
  unit: z.string().nullable(),
  recorded_at: z.string().datetime(),
});

export type Metric = z.infer<typeof MetricSchema>;

export const ArtifactSchema = z.object({
  id: z.string(),
  artifact_type: ArtifactTypeSchema,
  uri: z.string(),
  description: z.string().nullable(),
  created_at: z.string().datetime(),
});

export type Artifact = z.infer<typeof ArtifactSchema>;

export const ExperimentSchema = z.object({
  id: z.string(),
  name: z.string(),
  dataset_version: z.string().nullable(),
  feature_set: z.array(FeatureRequestSchema).nullable(),
  target_config: z.array(TargetRequestSchema).nullable(),
  split_config: SplitConfigSchema.nullable(),
  model_type: z.string().nullable(),
  status: ExperimentStatusSchema,
  notes: z.string().nullable(),
  tags: z.array(z.string()),
  metrics: z.array(MetricSchema),
  artifacts: z.array(ArtifactSchema),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});

export type Experiment = z.infer<typeof ExperimentSchema>;

export const ExperimentSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  dataset_version: z.string().nullable(),
  model_type: z.string().nullable(),
  status: ExperimentStatusSchema,
  tags: z.array(z.string()),
  metric_count: z.number().int().nonnegative(),
  artifact_count: z.number().int().nonnegative(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});

export type ExperimentSummary = z.infer<typeof ExperimentSummarySchema>;

export const ExperimentListResponseSchema = z.object({
  experiments: z.array(ExperimentSummarySchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
  statuses: z.array(z.string()),
  artifact_types: z.array(z.string()),
});

export type ExperimentListResponse = z.infer<typeof ExperimentListResponseSchema>;
