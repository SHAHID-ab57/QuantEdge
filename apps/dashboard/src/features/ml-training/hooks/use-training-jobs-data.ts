'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  cancelTrainingJob,
  createTrainingJob,
  deleteTrainingJob,
  fetchModelAdapters,
  fetchTrainingJob,
  fetchTrainingJobs,
  runTrainingJob,
  type TrainingJobCreateBody,
  type TrainingJobListParams,
} from '@/lib/api/training';

/** Server state for the ML Training page — job list, detail, catalogue, and every mutation. */

const TRAINING_JOBS_KEY = ['training-jobs'] as const;

export function useTrainingJobs(params: TrainingJobListParams) {
  return useQuery({
    queryKey: [...TRAINING_JOBS_KEY, 'list', params],
    queryFn: () => fetchTrainingJobs(params),
  });
}

/**
 * Polls every 3s while the job is running so the status monitor and logs
 * reflect pipeline progress without the user manually refreshing — the run
 * itself executes synchronously server-side (no worker/queue service
 * exists yet), so a short poll is how a client observes it "live."
 */
export function useTrainingJob(id: string | null) {
  return useQuery({
    queryKey: [...TRAINING_JOBS_KEY, 'detail', id],
    queryFn: () => fetchTrainingJob(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  });
}

export function useModelAdapters() {
  return useQuery({
    queryKey: [...TRAINING_JOBS_KEY, 'models'],
    queryFn: () => fetchModelAdapters(),
    staleTime: Infinity,
  });
}

function useInvalidateTrainingJobs() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: TRAINING_JOBS_KEY });
}

export function useCreateTrainingJob() {
  const invalidate = useInvalidateTrainingJobs();
  return useMutation({
    mutationFn: (body: TrainingJobCreateBody) => createTrainingJob(body),
    onSuccess: invalidate,
  });
}

export function useDeleteTrainingJob() {
  const invalidate = useInvalidateTrainingJobs();
  return useMutation({
    mutationFn: (id: string) => deleteTrainingJob(id),
    onSuccess: invalidate,
  });
}

export function useRunTrainingJob() {
  const invalidate = useInvalidateTrainingJobs();
  return useMutation({
    mutationFn: (id: string) => runTrainingJob(id),
    onSuccess: invalidate,
  });
}

export function useCancelTrainingJob() {
  const invalidate = useInvalidateTrainingJobs();
  return useMutation({
    mutationFn: (id: string) => cancelTrainingJob(id),
    onSuccess: invalidate,
  });
}
