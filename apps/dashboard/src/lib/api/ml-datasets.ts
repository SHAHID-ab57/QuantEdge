import { apiClient } from './client';
import type { BuildDatasetParams } from './features';
import {
  MLDatasetBuildDetailResponseSchema,
  MLDatasetBuildListResponseSchema,
  MLDatasetResponseSchema,
  TargetCatalogResponseSchema,
  TargetDTOSchema,
  type MLDatasetBuildDetailResponse,
  type MLDatasetBuildListResponse,
  type MLDatasetResponse,
  type TargetCatalogResponse,
  type TargetDTO,
} from '@/types/api/ml-datasets';

/** The full target catalogue: every prediction-target generator the pipeline can run. */
export async function fetchTargets(): Promise<TargetCatalogResponse> {
  const { data } = await apiClient.get('/api/v1/ml/targets');
  return TargetCatalogResponseSchema.parse(data);
}

/** One target generator's metadata. */
export async function fetchTarget(name: string): Promise<TargetDTO> {
  const { data } = await apiClient.get(`/api/v1/ml/targets/${encodeURIComponent(name)}`);
  return TargetDTOSchema.parse(data);
}

export interface TargetRequestBody {
  target: string;
  params?: Record<string, string>;
}

/**
 * Everything a dataset build request needs, plus targets and a
 * train/validation/test split. Extends `BuildDatasetParams` rather than
 * duplicating its fields — the same market/timeframe/range/feature
 * selection that builds a plain feature dataset also builds a fully
 * versioned, split, validated ML dataset; only `targets` and the split
 * ratios are new.
 */
export interface BuildMLDatasetParams extends BuildDatasetParams {
  targets: TargetRequestBody[];
  drop_undefined_targets?: boolean;
  split_train?: number;
  split_validation?: number;
  split_test?: number;
}

/** Build a versioned, split, validated ML dataset for one market/timeframe/range. */
export async function buildMLDataset(
  symbol: string,
  params: BuildMLDatasetParams,
): Promise<MLDatasetResponse> {
  const { data } = await apiClient.post(
    `/api/v1/markets/${encodeURIComponent(symbol)}/ml/dataset`,
    params,
  );
  return MLDatasetResponseSchema.parse(data);
}

/**
 * Download a complete ML dataset as a CSV or JSON file.
 *
 * Fetched from the backend rather than serialized from the preview already
 * on screen, for the same reason `exportFeatureDataset` is: the preview is
 * capped for rendering, while an export must contain the full, unsplit
 * matrix plus its per-row split label — so `preview_rows` is stripped
 * rather than merely ignored server-side.
 */
export async function exportMLDataset(
  symbol: string,
  params: BuildMLDatasetParams,
  format: 'csv' | 'json',
): Promise<Blob> {
  const full: BuildMLDatasetParams = { ...params };
  delete full.preview_rows;
  const { data } = await apiClient.post(
    `/api/v1/markets/${encodeURIComponent(symbol)}/ml/dataset/export?format=${format}`,
    full,
    { responseType: 'blob' },
  );
  return data as Blob;
}

export interface MLDatasetBuildListParams {
  symbol?: string;
  timeframe?: string;
  quality_passed?: boolean;
  sort?: 'symbol' | 'timeframe' | 'row_count' | 'created_at';
  dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

/** Dataset History's list view — every past ML dataset build, paginated. */
export async function fetchMLDatasetBuilds(
  params: MLDatasetBuildListParams = {},
): Promise<MLDatasetBuildListResponse> {
  const { data } = await apiClient.get('/api/v1/ml/dataset-builds', { params });
  return MLDatasetBuildListResponseSchema.parse(data);
}

/** Reopen one past ML dataset build — its full, untruncated matrix. */
export async function fetchMLDatasetBuild(id: string): Promise<MLDatasetBuildDetailResponse> {
  const { data } = await apiClient.get(`/api/v1/ml/dataset-builds/${encodeURIComponent(id)}`);
  return MLDatasetBuildDetailResponseSchema.parse(data);
}

/** Remove one past build from Dataset History. Never touches the underlying candles. */
export async function deleteMLDatasetBuild(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/ml/dataset-builds/${encodeURIComponent(id)}`);
}
