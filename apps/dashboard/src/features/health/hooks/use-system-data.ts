'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchSystemHealth, fetchSystemMetrics, fetchSystemStatus } from '@/lib/api/system';

export const SYSTEM_REFRESH_INTERVAL_MS = 10_000;

export function useSystemHealth() {
  return useQuery({
    queryKey: ['system', 'health'],
    queryFn: fetchSystemHealth,
    refetchInterval: SYSTEM_REFRESH_INTERVAL_MS,
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ['system', 'status'],
    queryFn: fetchSystemStatus,
    refetchInterval: SYSTEM_REFRESH_INTERVAL_MS,
  });
}

export function useSystemMetrics() {
  return useQuery({
    queryKey: ['system', 'metrics'],
    queryFn: fetchSystemMetrics,
    refetchInterval: SYSTEM_REFRESH_INTERVAL_MS,
  });
}
