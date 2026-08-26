import { apiClient } from './client';
import {
  ModelAdapterCatalogResponseSchema,
  TrainingJobListResponseSchema,
  TrainingJobSchema,
  type ModelAdapterCatalogResponse,
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
  hyperparameters?: Record<string, unknown>;
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
