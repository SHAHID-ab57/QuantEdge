'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteBenchmarkRun,
  fetchBenchmarkHistory,
  fetchBenchmarkRun,
  fetchMetricCatalog,
  runBenchmark,
  type BenchmarkHistoryListParams,
  type BenchmarkRequestBody,
} from '@/lib/api/evaluation';

/** Server state for the Model Evaluation & Benchmarking page — the metric
 * catalogue (a reference, fetched once), the benchmark comparison
 * (triggered on demand; a benchmark is a request-response comparison, not a
 * persisted resource, so it is a mutation rather than a query), and
 * Benchmark History (a real persisted, listable/reopenable resource). */

const BENCHMARK_HISTORY_KEY = ['evaluation', 'history'] as const;

export function useMetricCatalog() {
  return useQuery({
    queryKey: ['evaluation', 'metrics'],
    queryFn: () => fetchMetricCatalog(),
    staleTime: Infinity,
  });
}

export function useBenchmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BenchmarkRequestBody) => runBenchmark(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: BENCHMARK_HISTORY_KEY }),
  });
}

export function useBenchmarkHistory(params: BenchmarkHistoryListParams) {
  return useQuery({
    queryKey: [...BENCHMARK_HISTORY_KEY, 'list', params],
    queryFn: () => fetchBenchmarkHistory(params),
  });
}

export function useBenchmarkRun(id: string | null) {
  return useQuery({
    queryKey: [...BENCHMARK_HISTORY_KEY, 'detail', id],
    queryFn: () => fetchBenchmarkRun(id as string),
    enabled: Boolean(id),
  });
}

export function useDeleteBenchmarkRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteBenchmarkRun(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: BENCHMARK_HISTORY_KEY }),
  });
}
