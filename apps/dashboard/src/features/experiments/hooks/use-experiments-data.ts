'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createArtifact,
  createExperiment,
  createMetric,
  deleteArtifact,
  deleteExperiment,
  deleteMetric,
  fetchExperiment,
  fetchExperiments,
  updateExperiment,
  type ArtifactWriteBody,
  type ExperimentListParams,
  type ExperimentWriteBody,
  type MetricWriteBody,
} from '@/lib/api/experiments';

/** Server state for the Experiment Management pages — list, detail, and every mutation. */

const EXPERIMENTS_KEY = ['experiments'] as const;

export function useExperiments(params: ExperimentListParams) {
  return useQuery({
    queryKey: [...EXPERIMENTS_KEY, 'list', params],
    queryFn: () => fetchExperiments(params),
  });
}

export function useExperiment(id: string) {
  return useQuery({
    queryKey: [...EXPERIMENTS_KEY, 'detail', id],
    queryFn: () => fetchExperiment(id),
    enabled: id.length > 0,
  });
}

/**
 * Every mutation below invalidates the whole `experiments` query family
 * (list and every detail) rather than hand-patching the cache: an
 * experiment registry is low-traffic and rarely has more than a handful
 * of open queries at once, so the simplicity of "just refetch" outweighs
 * optimistic-update bookkeeping here.
 */
function useInvalidateExperiments() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: EXPERIMENTS_KEY });
}

export function useCreateExperiment() {
  const invalidate = useInvalidateExperiments();
  return useMutation({
    mutationFn: (body: ExperimentWriteBody) => createExperiment(body),
    onSuccess: invalidate,
  });
}

export function useUpdateExperiment() {
  const invalidate = useInvalidateExperiments();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ExperimentWriteBody }) =>
      updateExperiment(id, body),
    onSuccess: invalidate,
  });
}

export function useDeleteExperiment() {
  const invalidate = useInvalidateExperiments();
  return useMutation({
    mutationFn: (id: string) => deleteExperiment(id),
    onSuccess: invalidate,
  });
}

export function useCreateMetric() {
  const invalidate = useInvalidateExperiments();
  return useMutation({
    mutationFn: ({ experimentId, body }: { experimentId: string; body: MetricWriteBody }) =>
      createMetric(experimentId, body),
    onSuccess: invalidate,
  });
}

export function useDeleteMetric() {
  const invalidate = useInvalidateExperiments();
  return useMutation({
    mutationFn: ({ experimentId, metricId }: { experimentId: string; metricId: string }) =>
      deleteMetric(experimentId, metricId),
    onSuccess: invalidate,
  });
}

export function useCreateArtifact() {
  const invalidate = useInvalidateExperiments();
  return useMutation({
    mutationFn: ({ experimentId, body }: { experimentId: string; body: ArtifactWriteBody }) =>
      createArtifact(experimentId, body),
    onSuccess: invalidate,
  });
}

export function useDeleteArtifact() {
  const invalidate = useInvalidateExperiments();
  return useMutation({
    mutationFn: ({ experimentId, artifactId }: { experimentId: string; artifactId: string }) =>
      deleteArtifact(experimentId, artifactId),
    onSuccess: invalidate,
  });
}
