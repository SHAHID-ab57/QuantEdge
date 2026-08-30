import { apiClient } from './client';
import {
  ModelAdapterCatalogResponseSchema,
  TrainingArtifactListResponseSchema,
  TrainingJobListResponseSchema,
  TrainingJobSchema,
  type ModelAdapterCatalogResponse,
  type TrainingArtifactListResponse,
  type TrainingJob,
  type TrainingJobListResponse,
  type TrainingJobStatus,
} from '@/types/api/training';

export interface TrainingJobListParams {
  experiment_id?: string;
  status?: TrainingJobStatus;
  model_type?: string;
  sort?: 'status' | 'model_type' | 'created_at' | 'updated_at' | 'started_at' | 'completed_at';
  dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export async function fetchTrainingJobs(
  params: TrainingJobListParams = {},
): Promise<TrainingJobListResponse> {
  const { data } = await apiClient.get('/api/v1/training-jobs', { params });
  return TrainingJobListResponseSchema.parse(data);
}

export async function fetchTrainingJob(id: string): Promise<TrainingJob> {
  const { data } = await apiClient.get(`/api/v1/training-jobs/${encodeURIComponent(id)}`);
  return TrainingJobSchema.parse(data);
}

export interface TrainingJobCreateBody {
  experiment_id: string;
  model_type: string;
  dataset_version?: string | null;
  symbol?: string | null;
  timeframe?: string | null;
  target_column?: string | null;
  hyperparameters?: Record<string, unknown>;
  /** Z-score normalize numeric feature columns (fit on the train split alone)
   * before a requires_real_data adapter trains/predicts. Defaults to `true`
   * server-side if omitted. */
  normalize_features?: boolean;
}

export async function createTrainingJob(body: TrainingJobCreateBody): Promise<TrainingJob> {
  const { data } = await apiClient.post('/api/v1/training-jobs', body);
  return TrainingJobSchema.parse(data);
}

export async function deleteTrainingJob(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/training-jobs/${encodeURIComponent(id)}`);
}

export async function runTrainingJob(id: string): Promise<TrainingJob> {
  const { data } = await apiClient.post(`/api/v1/training-jobs/${encodeURIComponent(id)}/run`);
  return TrainingJobSchema.parse(data);
}

export async function cancelTrainingJob(id: string): Promise<TrainingJob> {
  const { data } = await apiClient.post(`/api/v1/training-jobs/${encodeURIComponent(id)}/cancel`);
  return TrainingJobSchema.parse(data);
}

export async function fetchModelAdapters(): Promise<ModelAdapterCatalogResponse> {
  const { data } = await apiClient.get('/api/v1/training-jobs/models');
  return ModelAdapterCatalogResponseSchema.parse(data);
}

/** Every downloadable artifact (model.joblib, metrics.json, plots, ...) a completed
 * job's training run produced — the Artifact Management download surface. */
export async function fetchTrainingArtifacts(jobId: string): Promise<TrainingArtifactListResponse> {
  const { data } = await apiClient.get(
    `/api/v1/training-jobs/${encodeURIComponent(jobId)}/artifacts`,
  );
  return TrainingArtifactListResponseSchema.parse(data);
}

/** Download one artifact's raw file content, by its `download_url` from
 * `fetchTrainingArtifacts` — the same `responseType: 'blob'` pattern
 * `exportMLDataset` already uses for a server-generated file. */
export async function downloadTrainingArtifact(downloadUrl: string): Promise<Blob> {
  const { data } = await apiClient.get(downloadUrl, { responseType: 'blob' });
  return data as Blob;
}
