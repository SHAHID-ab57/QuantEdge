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
 * `staleTime` stays long: most sources' own *values* rarely move (even
 * Fear & Greed only updates once a day). But `health_status`,
 * `last_attempt_at`, and `next_sync_at` change on every scheduler tick —
 * that's the whole point of surfacing them on this page — so a moderate
 * `refetchInterval` keeps the sync-timing display honestly live without
 * polling as aggressively as the Health page's 10s (nothing here needs
 * sub-minute precision).
 */
export function useConnectorCatalog() {
  return useQuery({
    queryKey: ['connectors', 'catalogue'],
    queryFn: fetchConnectors,
    staleTime: 5 * 60_000,
    refetchInterval: 30_000,
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
