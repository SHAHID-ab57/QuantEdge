import { apiClient } from './client';
import {
  FeatureCatalogSchema,
  FeatureDatasetSchema,
  FeatureSchema,
  type Feature,
  type FeatureCatalog,
  type FeatureDataset,
} from '@/types/api/features';

/** The full feature catalogue, including each generator's parameter specs. */
export async function fetchFeatures(): Promise<FeatureCatalog> {
  const { data } = await apiClient.get('/api/v1/features');
  return FeatureCatalogSchema.parse(data);
}

/** One feature generator's metadata. */
export async function fetchFeature(name: string): Promise<Feature> {
  const { data } = await apiClient.get(`/api/v1/features/${encodeURIComponent(name)}`);
  return FeatureSchema.parse(data);
}

export interface FeatureRequestBody {
  feature: string;
  params?: Record<string, string>;
}

export interface BuildDatasetParams {
  timeframe: string;
  start?: string;
  end?: string;
  limit?: number;
  features: FeatureRequestBody[];
  /** Drop rows where any feature is still in warmup. Defaults to true server-side. */
  drop_warmup?: boolean;
  /** Cap rows in the response for display; `meta` still describes the full dataset. */
  preview_rows?: number;
}

/** Build a feature dataset for one market/timeframe/range. */
export async function buildFeatureDataset(
  symbol: string,
  params: BuildDatasetParams,
): Promise<FeatureDataset> {
  const { data } = await apiClient.post(
    `/api/v1/markets/${encodeURIComponent(symbol)}/features/dataset`,
    params,
  );
  return FeatureDatasetSchema.parse(data);
}

/**
 * Download a complete dataset as a CSV or JSON file.
 *
 * The export is fetched from the backend rather than serialized from the
 * preview already on screen, and that matters: the preview is deliberately
 * capped at a few hundred rows so a browser can render it, while an export
 * must contain everything. Building the file from the preview would ship a
 * silently truncated training set — so `preview_rows` is stripped here
 * rather than merely ignored server-side, making the intent explicit at
 * the call site too.
 */
export async function exportFeatureDataset(
  symbol: string,
  params: BuildDatasetParams,
  format: 'csv' | 'json',
): Promise<Blob> {
  const full: BuildDatasetParams = { ...params };
  delete full.preview_rows;
  const { data } = await apiClient.post(
    `/api/v1/markets/${encodeURIComponent(symbol)}/features/export?format=${format}`,
    full,
    { responseType: 'blob' },
  );
  return data as Blob;
}
