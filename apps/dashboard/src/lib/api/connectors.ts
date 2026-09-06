import type { z } from 'zod';
import { apiClient } from './client';
import {
  ConnectorCatalogSchema,
  ConnectorHistorySchema,
  type ConnectorCatalog,
  type ConnectorHistory,
} from '@/types/api/connectors';

async function getValidated<T>(path: string, schema: z.ZodType<T>, query?: string): Promise<T> {
  const { data } = await apiClient.get(query ? `${path}?${query}` : path);
  return schema.parse(data);
}

/** Every registered connector, each with its own most recent value. */
export function fetchConnectors(): Promise<ConnectorCatalog> {
  return getValidated('/api/v1/connectors', ConnectorCatalogSchema);
}

export interface ConnectorHistoryParams {
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
}

/** A page of one connector's stored history, oldest first. */
export function fetchConnectorHistory(
  source: string,
  params: ConnectorHistoryParams = {},
): Promise<ConnectorHistory> {
  const search = new URLSearchParams();
  if (params.start) search.set('start', params.start);
  if (params.end) search.set('end', params.end);
  if (params.limit !== undefined) search.set('limit', String(params.limit));
  if (params.offset !== undefined) search.set('offset', String(params.offset));
  return getValidated(
    `/api/v1/connectors/${encodeURIComponent(source)}/history`,
    ConnectorHistorySchema,
    search.toString(),
  );
}
