import { z } from 'zod';

/**
 * Wire schemas for the Machine Learning Training Framework API (see
 * `services/api/app/api/v1/endpoints/training.py` /
 * `services/api/app/schemas/training.py`). Every response is validated
 * against these before the app trusts it, matching `experiments.ts`'s
 * own convention.
 */

export const TRAINING_JOB_STATUSES = [
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled',
] as const;

export const TrainingJobStatusSchema = z.enum(TRAINING_JOB_STATUSES);

export type TrainingJobStatus = z.infer<typeof TrainingJobStatusSchema>;

export const TRAINING_JOB_STAGES = [
  'validate_dataset',
  'load_dataset',
  'initialize_model',
  'execute_training',
  'save_results',
  'update_experiment',
] as const;

export const TrainingJobStageSchema = z.enum(TRAINING_JOB_STAGES);

export type TrainingJobStage = z.infer<typeof TrainingJobStageSchema>;

export const TRAINING_LOG_LEVELS = ['debug', 'info', 'warning', 'error'] as const;

export const TrainingLogLevelSchema = z.enum(TRAINING_LOG_LEVELS);

export type TrainingLogLevel = z.infer<typeof TrainingLogLevelSchema>;

export const TrainingJobLogSchema = z.object({
  id: z.string(),
  level: TrainingLogLevelSchema,
  stage: TrainingJobStageSchema.nullable(),
  message: z.string(),
  logged_at: z.string().datetime(),
});

export type TrainingJobLog = z.infer<typeof TrainingJobLogSchema>;

export const TrainingJobSchema = z.object({
  id: z.string(),
  experiment_id: z.string(),
  dataset_version: z.string().nullable(),
  symbol: z.string().nullable(),
  timeframe: z.string().nullable(),
  target_column: z.string().nullable(),
  model_type: z.string(),
  hyperparameters: z.record(z.string(), z.unknown()),
  /** Whether numeric feature columns were (or will be) z-score normalized —
   * fit on the train split alone — before this job's model trains/predicts.
   * Ignored by an adapter whose requires_real_data is false. */
  normalize_features: z.boolean(),
  status: TrainingJobStatusSchema,
  current_stage: TrainingJobStageSchema.nullable(),
  error_message: z.string().nullable(),
  error_detail: z
    .object({
      reason: z.string(),
      affected_feature: z.string().nullable(),
      affected_rows: z.array(z.number()).nullable(),
      suggested_fix: z.string(),
    })
    .nullable()
    .optional(),
  result_summary: z.record(z.string(), z.unknown()).nullable(),
  started_at: z.string().datetime().nullable(),
  completed_at: z.string().datetime().nullable(),
  logs: z.array(TrainingJobLogSchema),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});

export type TrainingJob = z.infer<typeof TrainingJobSchema>;

export const TrainingJobSummarySchema = z.object({
  id: z.string(),
  experiment_id: z.string(),
  dataset_version: z.string().nullable(),
  model_type: z.string(),
  status: TrainingJobStatusSchema,
  current_stage: TrainingJobStageSchema.nullable(),
  log_count: z.number().int().nonnegative(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});

export type TrainingJobSummary = z.infer<typeof TrainingJobSummarySchema>;

export const TrainingJobListResponseSchema = z.object({
  jobs: z.array(TrainingJobSummarySchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
  statuses: z.array(z.string()),
  stages: z.array(z.string()),
});

export type TrainingJobListResponse = z.infer<typeof TrainingJobListResponseSchema>;

export const MODEL_KINDS = ['placeholder', 'classification', 'regression'] as const;

export const ModelKindSchema = z.enum(MODEL_KINDS);

export type ModelKind = z.infer<typeof ModelKindSchema>;

export const ModelAdapterSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
  framework: z.string(),
  model_kind: ModelKindSchema,
  requires_real_data: z.boolean(),
  hyperparameter_hints: z.array(z.string()),
  version: z.string(),
});

export type ModelAdapter = z.infer<typeof ModelAdapterSchema>;

export const ModelAdapterCatalogResponseSchema = z.object({
  adapters: z.array(ModelAdapterSchema),
});

export type ModelAdapterCatalogResponse = z.infer<typeof ModelAdapterCatalogResponseSchema>;

export const TrainingArtifactSchema = z.object({
  artifact_type: z.string(),
  filename: z.string(),
  content_type: z.string(),
  download_url: z.string(),
});

export type TrainingArtifact = z.infer<typeof TrainingArtifactSchema>;

export const TrainingArtifactListResponseSchema = z.object({
  job_id: z.string(),
  artifacts: z.array(TrainingArtifactSchema),
});

export type TrainingArtifactListResponse = z.infer<typeof TrainingArtifactListResponseSchema>;

export const TrainingJobPredictResponseSchema = z.object({
  predictions: z.array(z.unknown()),
  feature_columns: z.array(z.string()).nullable().optional(),
  classes: z.array(z.unknown()).nullable().optional(),
  probabilities: z.array(z.array(z.number())).nullable().optional(),
  confidence_levels: z.array(z.string()).nullable().optional(),
});

export type TrainingJobPredictResponse = z.infer<typeof TrainingJobPredictResponseSchema>;
