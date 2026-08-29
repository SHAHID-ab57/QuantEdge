import { apiClient } from './client';
import {
  BenchmarkResponseSchema,
  BenchmarkRunDetailResponseSchema,
  BenchmarkRunListResponseSchema,
  MetricCatalogResponseSchema,
  type BenchmarkResponse,
  type BenchmarkRunDetailResponse,
  type BenchmarkRunListResponse,
  type MetricCatalogResponse,
} from '@/types/api/evaluation';

/** The registered metric catalogue — the Evaluation Engine's extension point,
 * shown on `/ml/evaluation` as a reference of every metric a benchmark can compare. */
export async function fetchMetricCatalog(): Promise<MetricCatalogResponse> {
  const { data } = await apiClient.get('/api/v1/evaluation/metrics');
  return MetricCatalogResponseSchema.parse(data);
}

export interface BenchmarkRequestBody {
  dataset_version?: string;
  target_column?: string;
  experiment_ids?: string[];
}

/** Compare completed training jobs matching `body` — a read-only comparison over
 * metrics already recorded during training, never a re-computation. */
export async function runBenchmark(body: BenchmarkRequestBody): Promise<BenchmarkResponse> {
  const { data } = await apiClient.post('/api/v1/evaluation/benchmark', body);
  return BenchmarkResponseSchema.parse(data);
}

export interface BenchmarkHistoryListParams {
  dataset_version?: string;
  target_column?: string;
  sort?: 'dataset_version' | 'target_column' | 'candidate_count' | 'created_at';
  dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

/** Benchmark History's list view — every past comparison this platform has recorded. */
export async function fetchBenchmarkHistory(
  params: BenchmarkHistoryListParams = {},
): Promise<BenchmarkRunListResponse> {
  const { data } = await apiClient.get('/api/v1/evaluation/history', { params });
  return BenchmarkRunListResponseSchema.parse(data);
}

/** Reopen one past benchmark run — its exact request and response, verbatim. */
export async function fetchBenchmarkRun(id: string): Promise<BenchmarkRunDetailResponse> {
  const { data } = await apiClient.get(`/api/v1/evaluation/history/${encodeURIComponent(id)}`);
  return BenchmarkRunDetailResponseSchema.parse(data);
}

/** Remove one past run from Benchmark History — the underlying training jobs are untouched. */
export async function deleteBenchmarkRun(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/evaluation/history/${encodeURIComponent(id)}`);
}
