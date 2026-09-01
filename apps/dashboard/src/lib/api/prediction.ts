import { apiClient } from './client';
import {
  PredictionListResponseSchema,
  PredictionResponseSchema,
  type PredictionListResponse,
  type PredictionResponse,
} from '@/types/api/prediction';

export interface PredictionRunBody {
  training_job_id: string;
  symbol: string;
  /** ISO-8601. Omit for the latest available candle. */
  as_of?: string;
}

/** Reconstruct a live feature vector, predict, and persist the result. */
export async function runPrediction(body: PredictionRunBody): Promise<PredictionResponse> {
  const { data } = await apiClient.post('/api/v1/predictions/run', body);
  return PredictionResponseSchema.parse(data);
}

/** Reopen one past prediction — its exact result, verbatim. */
export async function fetchPrediction(id: string): Promise<PredictionResponse> {
  const { data } = await apiClient.get(`/api/v1/predictions/${encodeURIComponent(id)}`);
  return PredictionResponseSchema.parse(data);
}

export interface PredictionListParams {
  training_job_id?: string;
  experiment_id?: string;
  symbol?: string;
  sort?: 'symbol' | 'as_of' | 'created_at';
  dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

/** Prediction History's list view — every past prediction this platform has recorded. */
export async function fetchPredictions(
  params: PredictionListParams = {},
): Promise<PredictionListResponse> {
  const { data } = await apiClient.get('/api/v1/predictions', { params });
  return PredictionListResponseSchema.parse(data);
}
