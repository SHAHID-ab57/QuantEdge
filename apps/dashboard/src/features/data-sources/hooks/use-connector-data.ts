'use client';

import { useQuery } from '@tanstack/react-query';
import {
  fetchConnectorHistory,
  fetchConnectors,
  type ConnectorHistoryParams,
} from '@/lib/api/connectors';

/** How many recent points a card's trend sparkline requests. */
export const HISTORY_SPARKLINE_LIMIT = 90;

/** Every registered connector, each with its own most recent value.
 *
 * A long `staleTime`: the catalogue only changes when the backend
 * registers a new connector, and even Fear & Greed's own latest value
 * only updates once a day — refetching this every few seconds would just
 * be wasted requests for data that hasn't moved.
 */
export function useConnectorCatalog() {
  return useQuery({
    queryKey: ['connectors', 'catalogue'],
    queryFn: fetchConnectors,
    staleTime: 5 * 60_000,
  });
}

/** One connector's recent history, for its own card's trend sparkline. */
export function useConnectorHistory(source: string, params: ConnectorHistoryParams = {}) {
  return useQuery({
    queryKey: ['connectors', source, 'history', params],
    queryFn: () => fetchConnectorHistory(source, params),
    staleTime: 5 * 60_000,
  });
}
