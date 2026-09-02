'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  cancelTrainingJob,
  createTrainingJob,
  deleteTrainingJob,
  fetchModelAdapters,
  fetchTrainingArtifacts,
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
 * reflect pipeline progress without the user manually refreshing. The run
 * itself now executes in a background task server-side (see
 * `useRunTrainingJob` below) — the mutation resolves as soon as the job is
 * validated and transitioned to 'running', well before the pipeline
 * finishes, so this poll is what actually shows progress from there.
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

/**
 * Starts the run — the mutation resolves once the job is validated and
 * transitioned to 'running' (the server responds before the pipeline
 * itself finishes), not once training completes. `invalidate` refetches
 * the job detail immediately after, so the dialog shows 'running' right
 * away; `useTrainingJob`'s own 3s poll takes over from there until the job
 * settles into 'completed' or 'failed'.
 */
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

/** Every downloadable artifact a completed job's training run produced — the
 * Artifact Management panel's data source. */
export function useTrainingArtifacts(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: [...TRAINING_JOBS_KEY, 'artifacts', jobId],
    queryFn: () => fetchTrainingArtifacts(jobId as string),
    enabled: Boolean(jobId) && enabled,
  });
}
