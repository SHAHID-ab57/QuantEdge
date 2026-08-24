'use client';

import { useQuery } from '@tanstack/react-query';
import { calculateIndicatorBatch } from '@/lib/api/indicators';
import type { OverlayConfig } from '../store/use-overlay-store';

export interface UseOverlayCalculationsInput {
  symbol: string | null;
  timeframe: string | null;
  start?: string;
  end?: string;
  limit?: number;
  overlays: readonly OverlayConfig[];
}

/**
 * Calculates every *enabled* overlay in one request via the batch API
 * (`calculateIndicatorBatch`), sharing one candle load across all of them
 * on the backend rather than firing one request per overlay.
 *
 * The query key is built from the enabled overlays sorted by id, so
 * reordering the list (e.g. toggling one off and back on) never produces
 * a spuriously different key. Disabled overlays are left out of the
 * request entirely — nothing is computed for them until re-enabled, at
 * which point the engine's own result cache serves an unchanged
 * configuration instantly rather than this hook trying to reinvent that
 * caching on the frontend.
 */
export function useOverlayCalculations({
  symbol,
  timeframe,
  start,
  end,
  limit,
  overlays,
}: UseOverlayCalculationsInput) {
  const enabled = [...overlays]
    .filter((overlay) => overlay.enabled)
    .sort((a, b) => a.id.localeCompare(b.id));

  const requestKey = enabled.map((overlay) => ({
    indicator: overlay.indicator,
    params: overlay.params,
  }));

  return useQuery({
    queryKey: [
      'indicator-overlays',
      'batch',
      symbol,
      timeframe,
      start ?? null,
      end ?? null,
      limit ?? null,
      requestKey,
    ],
    queryFn: () =>
      calculateIndicatorBatch(symbol!, {
        timeframe: timeframe!,
        start,
        end,
        limit,
        requests: requestKey,
      }),
    enabled: Boolean(symbol && timeframe && enabled.length > 0),
    staleTime: 30_000,
    retry: false,
  });
}
