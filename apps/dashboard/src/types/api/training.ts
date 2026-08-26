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
  model_type: z.string(),
  hyperparameters: z.record(z.string(), z.unknown()),
  status: TrainingJobStatusSchema,
  current_stage: TrainingJobStageSchema.nullable(),
  error_message: z.string().nullable(),
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

export const ModelAdapterSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
  framework: z.string(),
  hyperparameter_hints: z.array(z.string()),
  version: z.string(),
});

export type ModelAdapter = z.infer<typeof ModelAdapterSchema>;

export const ModelAdapterCatalogResponseSchema = z.object({
  adapters: z.array(ModelAdapterSchema),
});

export type ModelAdapterCatalogResponse = z.infer<typeof ModelAdapterCatalogResponseSchema>;
