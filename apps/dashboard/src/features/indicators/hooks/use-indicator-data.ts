'use client';

import { useQuery } from '@tanstack/react-query';
import { calculateIndicator, fetchIndicators } from '@/lib/api/indicators';

/**
 * The indicator catalogue. Cached aggressively: the registry only changes
 * when the backend is redeployed, never during a session.
 */
export function useIndicatorCatalog() {
  return useQuery({
    queryKey: ['indicators', 'catalog'],
    queryFn: fetchIndicators,
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
  });
}

export interface IndicatorRequest {
  symbol: string;
  indicator: string;
  timeframe: string;
  params: Record<string, string | number | boolean>;
  limit?: number;
}

/**
 * Runs one indicator calculation.
 *
 * Deliberately `enabled`-gated on an explicit request object rather than
 * firing on every form keystroke: a calculation is a real backend query
 * (it reads candles), and a researcher changing a period from 20 to 200
 * would otherwise fire four requests on the way there. `IndicatorsPage`
 * only builds a request when the form is submitted.
 *
 * `retry: false` because the failures this endpoint produces are almost
 * all deterministic (an out-of-range parameter, too little data, an
 * unknown symbol) — retrying them just delays showing the researcher a
 * message that will not change.
 */
export function useIndicatorCalculation(request: IndicatorRequest | null) {
  return useQuery({
    queryKey: ['indicators', 'calculate', request],
    queryFn: () =>
      calculateIndicator(request!.symbol, request!.indicator, {
        timeframe: request!.timeframe,
        params: request!.params,
        limit: request!.limit,
      }),
    enabled: request !== null,
    retry: false,
    staleTime: 60_000,
  });
}
