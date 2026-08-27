'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  buildMLDataset,
  deleteMLDatasetBuild,
  exportMLDataset,
  fetchMLDatasetBuild,
  fetchMLDatasetBuilds,
  fetchTargets,
  type BuildMLDatasetParams,
  type MLDatasetBuildListParams,
} from '@/lib/api/ml-datasets';

/**
 * Server state for the ML Dataset Builder page.
 *
 * Market/timeframe lists and the feature catalogue are deliberately *not*
 * re-fetched here — the page reuses `useMarkets`/`useTimeframes` (History
 * module) and `useFeatureCatalog` (Feature Engineering module), exactly as
 * the Dataset Validation page does. A second copy would double the
 * requests and could show a different list on two pages of the same app.
 */

/** How many rows the preview table requests. */
export const PREVIEW_ROWS = 200;

export function useTargetCatalog() {
  return useQuery({
    queryKey: ['ml-datasets', 'targets'],
    queryFn: fetchTargets,
    // The target catalogue only changes when the backend deploys a new
    // generator, so it is worth caching for far longer than market data.
    staleTime: 5 * 60_000,
  });
}

export interface MLDatasetRequest {
  symbol: string;
  params: BuildMLDatasetParams;
}

/**
 * Building an ML dataset is a *mutation*, not a query, for the same reason
 * `useBuildDataset` is one: it is an explicit, potentially expensive,
 * user-initiated action (features, then targets, then validation, then a
 * split all run server-side) — never something that should silently
 * re-run on remount or a stale-time expiry.
 */
const DATASET_HISTORY_KEY = ['ml-datasets', 'history'] as const;

export function useBuildMLDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ symbol, params }: MLDatasetRequest) => buildMLDataset(symbol, params),
    // Every successful build is also persisted to Dataset History
    // server-side (see `MLDatasetService.build_dataset`) — invalidating here
    // means a researcher who then opens the history list sees it immediately,
    // without a manual refresh.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DATASET_HISTORY_KEY }),
  });
}

export interface MLDatasetExportRequest extends MLDatasetRequest {
  format: 'csv' | 'json';
}

export function useExportMLDataset() {
  return useMutation({
    mutationFn: ({ symbol, params, format }: MLDatasetExportRequest) =>
      exportMLDataset(symbol, params, format),
  });
}

/** Dataset History's list view — every past ML dataset build, paginated. */
export function useMLDatasetBuilds(params: MLDatasetBuildListParams) {
  return useQuery({
    queryKey: [...DATASET_HISTORY_KEY, 'list', params],
    queryFn: () => fetchMLDatasetBuilds(params),
  });
}

/** Reopen one past ML dataset build — its full, untruncated matrix. */
export function useMLDatasetBuild(id: string | null) {
  return useQuery({
    queryKey: [...DATASET_HISTORY_KEY, 'detail', id],
    queryFn: () => fetchMLDatasetBuild(id as string),
    enabled: Boolean(id),
  });
}

export function useDeleteMLDatasetBuild() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteMLDatasetBuild(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DATASET_HISTORY_KEY }),
  });
}
