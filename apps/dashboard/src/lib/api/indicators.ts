import type { z } from 'zod';
import { apiClient } from './client';
import {
  IndicatorCalculationSchema,
  IndicatorCatalogSchema,
  IndicatorSchema,
  type Indicator,
  type IndicatorCalculation,
  type IndicatorCatalog,
} from '@/types/api/indicators';

async function getValidated<T>(path: string, schema: z.ZodType<T>, query?: string): Promise<T> {
  const { data } = await apiClient.get(query ? `${path}?${query}` : path);
  return schema.parse(data);
}

/** The full indicator catalogue, including each indicator's parameter specs. */
export function fetchIndicators(): Promise<IndicatorCatalog> {
  return getValidated('/api/v1/indicators', IndicatorCatalogSchema);
}

/** One indicator's metadata. */
export function fetchIndicator(name: string): Promise<Indicator> {
  return getValidated(`/api/v1/indicators/${encodeURIComponent(name)}`, IndicatorSchema);
}

export interface CalculateIndicatorParams {
  timeframe: string;
  start?: string;
  end?: string;
  limit?: number;
  /**
   * Indicator-specific parameters, serialized straight into the query
   * string. Deliberately untyped here: the accepted set is defined by the
   * indicator's own published specs, not by this client — which is what
   * lets a new backend indicator work with no change on this side.
   */
  params?: Record<string, string | number | boolean>;
}

/** Run one indicator over a market's stored candles. */
export function calculateIndicator(
  symbol: string,
  indicator: string,
  { timeframe, start, end, limit, params = {} }: CalculateIndicatorParams,
): Promise<IndicatorCalculation> {
  const search = new URLSearchParams({ timeframe });
  if (start) search.set('start', start);
  if (end) search.set('end', end);
  if (limit !== undefined) search.set('limit', String(limit));
  for (const [key, value] of Object.entries(params)) {
    search.set(key, String(value));
  }
  return getValidated(
    `/api/v1/markets/${encodeURIComponent(symbol)}/indicators/${encodeURIComponent(indicator)}`,
    IndicatorCalculationSchema,
    search.toString(),
  );
}
