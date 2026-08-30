'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import {
  buildFeatureDataset,
  computeFeatureCorrelation,
  computeFeatureStatistics,
  exportFeatureDataset,
  fetchFeatureLineage,
  fetchFeatures,
  type BuildDatasetParams,
} from '@/lib/api/features';

/**
 * Server state for the Feature Engineering page.
 *
 * Market and timeframe lists are deliberately *not* re-fetched here — the
 * page reuses `useMarkets`/`useTimeframes` from the History feature module,
 * which already own those queries and their cache keys. A second copy would
 * double the requests and could show a different market list on two pages
 * of the same app.
 */

/** How many rows the preview table requests. */
export const PREVIEW_ROWS = 200;

export function useFeatureCatalog() {
  return useQuery({
    queryKey: ['features', 'catalogue'],
    queryFn: fetchFeatures,
    // The catalogue only changes when the backend deploys new generators,
    // so it is worth caching for far longer than market data.
    staleTime: 5 * 60_000,
  });
}

export interface DatasetRequest {
  symbol: string;
  params: BuildDatasetParams;
}

/**
 * Building a dataset is a *mutation*, not a query, despite reading data.
 *
 * It is an explicit, expensive, user-initiated action with a large
 * response — exactly what a researcher expects to happen when they press
 * "Build", and never as a side effect of changing a form field. Modelling
 * it as a query would make TanStack Query refetch it on remount and on key
 * changes, quietly re-running a heavy computation nobody asked for.
 */
export function useBuildDataset() {
  return useMutation({
    mutationFn: ({ symbol, params }: DatasetRequest) => buildFeatureDataset(symbol, params),
  });
}

export interface ExportRequest extends DatasetRequest {
  format: 'csv' | 'json';
}

export function useExportDataset() {
  return useMutation({
    mutationFn: ({ symbol, params, format }: ExportRequest) =>
      exportFeatureDataset(symbol, params, format),
  });
}

/** The whole feature registry's dependency graph — as static as the catalogue
 * itself (only changes when the backend deploys a generator declaring a new
 * dependency), so it shares the same long `staleTime`. */
export function useFeatureLineage() {
  return useQuery({
    queryKey: ['features', 'lineage'],
    queryFn: fetchFeatureLineage,
    staleTime: 5 * 60_000,
  });
}

/** Correlating a dataset's numeric columns is a mutation, not a query, for the
 * same reason `useBuildDataset` is: an explicit, potentially expensive,
 * user-initiated action over a request the caller already built. */
export function useComputeCorrelation() {
  return useMutation({
    mutationFn: ({ symbol, params }: DatasetRequest) => computeFeatureCorrelation(symbol, params),
  });
}

export function useComputeStatistics() {
  return useMutation({
    mutationFn: ({ symbol, params }: DatasetRequest) => computeFeatureStatistics(symbol, params),
  });
}
