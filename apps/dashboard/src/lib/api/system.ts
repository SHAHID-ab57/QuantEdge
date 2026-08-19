import type { z } from 'zod';
import { apiClient } from './client';
import {
  SystemHealthSchema,
  SystemMetricsSchema,
  SystemStatusSchema,
  type SystemHealth,
  type SystemMetrics,
  type SystemStatus,
} from '@/types/api/system';

async function getValidated<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const { data } = await apiClient.get(path);
  return schema.parse(data);
}

export function fetchSystemHealth(): Promise<SystemHealth> {
  return getValidated('/api/v1/system/health', SystemHealthSchema);
}

export function fetchSystemStatus(): Promise<SystemStatus> {
  return getValidated('/api/v1/system/status', SystemStatusSchema);
}

export function fetchSystemMetrics(): Promise<SystemMetrics> {
  return getValidated('/api/v1/system/metrics', SystemMetricsSchema);
}
