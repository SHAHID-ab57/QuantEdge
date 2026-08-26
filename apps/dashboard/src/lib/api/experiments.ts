import { apiClient } from './client';
import {
  ArtifactSchema,
  ExperimentListResponseSchema,
  ExperimentSchema,
  MetricSchema,
  type Artifact,
  type ArtifactType,
  type Experiment,
  type ExperimentListResponse,
  type ExperimentStatus,
  type FeatureRequest,
  type Metric,
  type SplitConfig,
  type TargetRequest,
} from '@/types/api/experiments';

export interface ExperimentListParams {
  q?: string;
  status?: ExperimentStatus;
  model_type?: string;
  dataset_version?: string;
  tag?: string;
  sort?: 'name' | 'status' | 'model_type' | 'created_at' | 'updated_at';
  dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export async function fetchExperiments(
  params: ExperimentListParams = {},
): Promise<ExperimentListResponse> {
  const { data } = await apiClient.get('/api/v1/experiments', { params });
  return ExperimentListResponseSchema.parse(data);
}

export async function fetchExperiment(id: string): Promise<Experiment> {
  const { data } = await apiClient.get(`/api/v1/experiments/${encodeURIComponent(id)}`);
  return ExperimentSchema.parse(data);
}

export interface ExperimentWriteBody {
  name?: string;
  dataset_version?: string | null;
  feature_set?: FeatureRequest[] | null;
  target_config?: TargetRequest[] | null;
  split_config?: SplitConfig | null;
  model_type?: string | null;
  status?: ExperimentStatus;
  notes?: string | null;
  tags?: string[];
}

export async function createExperiment(body: ExperimentWriteBody): Promise<Experiment> {
  const { data } = await apiClient.post('/api/v1/experiments', body);
  return ExperimentSchema.parse(data);
}

export async function updateExperiment(id: string, body: ExperimentWriteBody): Promise<Experiment> {
  const { data } = await apiClient.patch(`/api/v1/experiments/${encodeURIComponent(id)}`, body);
  return ExperimentSchema.parse(data);
}

export async function deleteExperiment(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/experiments/${encodeURIComponent(id)}`);
}

export interface MetricWriteBody {
  name: string;
  value: number;
  unit?: string | null;
}

export async function createMetric(experimentId: string, body: MetricWriteBody): Promise<Metric> {
  const { data } = await apiClient.post(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/metrics`,
    body,
  );
  return MetricSchema.parse(data);
}

export async function deleteMetric(experimentId: string, metricId: string): Promise<void> {
  await apiClient.delete(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/metrics/${encodeURIComponent(metricId)}`,
  );
}

export interface ArtifactWriteBody {
  artifact_type: ArtifactType;
  uri: string;
  description?: string | null;
}

export async function createArtifact(
  experimentId: string,
  body: ArtifactWriteBody,
): Promise<Artifact> {
  const { data } = await apiClient.post(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/artifacts`,
    body,
  );
  return ArtifactSchema.parse(data);
}

export async function deleteArtifact(experimentId: string, artifactId: string): Promise<void> {
  await apiClient.delete(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/artifacts/${encodeURIComponent(artifactId)}`,
  );
}
