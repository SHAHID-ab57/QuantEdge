'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import {
  fetchValidationRules,
  validateDataset,
  type ValidateDatasetParams,
} from '@/lib/api/dataset-validation';

/**
 * Server state for the Dataset Validation page.
 *
 * Market/timeframe lists and the feature catalogue are deliberately *not*
 * re-fetched here — the page reuses `useMarkets`/`useTimeframes` (History
 * module) and `useFeatureCatalog` (Feature Engineering module), which
 * already own those queries and their cache keys. A second copy would
 * double the requests and could show a different market or feature list
 * on two pages of the same app.
 */

export function useValidationRuleCatalog() {
  return useQuery({
    queryKey: ['dataset-validation', 'rules'],
    queryFn: fetchValidationRules,
    // The rule catalogue only changes when the backend deploys a new rule,
    // so it is worth caching for far longer than market data.
    staleTime: 5 * 60_000,
  });
}

export interface ValidationRequest {
  symbol: string;
  params: ValidateDatasetParams;
}

/**
 * Running validation is a *mutation*, not a query, for the same reason
 * `useBuildDataset` is one: it is an explicit, potentially expensive,
 * user-initiated action (it builds the dataset first) — never something
 * that should silently re-run on remount or a stale-time expiry.
 */
export function useRunValidation() {
  return useMutation({
    mutationFn: ({ symbol, params }: ValidationRequest) => validateDataset(symbol, params),
  });
}
