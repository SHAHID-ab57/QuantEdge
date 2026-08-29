'use client';

import AddIcon from '@mui/icons-material/Add';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'next/navigation';
import { Section } from '@/components/section';
import { fetchExperiments } from '@/lib/api/experiments';
import type { TrainingJobListParams } from '@/lib/api/training';
import type { TrainingJobSummary } from '@/types/api/training';
import { CreateTrainingJobDialog } from './components/create-training-job-dialog';
import {
  TrainingJobFiltersBar,
  type TrainingJobFiltersValue,
} from './components/training-job-filters-bar';
import { TrainingJobDetailDialog } from './components/training-job-detail-dialog';
import { TrainingJobsTable } from './components/training-jobs-table';
import { useTrainingJobs } from './hooks/use-training-jobs-data';

const PAGE_SIZE = 20;

const INITIAL_FILTERS: TrainingJobFiltersValue = { experimentId: '', status: '' };

/**
 * The Machine Learning Training Framework's orchestration surface:
 * register, filter, run, monitor, and cancel training jobs against an
 * existing experiment. Implements no real model training — every job runs
 * the placeholder pipeline (`app/training/pipeline.py`); this page is a
 * thin view over that CRUD + lifecycle API, exactly like `/experiments` is
 * over the Experiment Management API.
 *
 * A `?jobId=` query param opens that job's detail dialog on load — the
 * Model Evaluation & Benchmarking page's comparison table links here this
 * way for its "Open Training Job" deep link, rather than duplicating this
 * page's own detail view.
 */
export function MLTrainingPage() {
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<TrainingJobFiltersValue>(INITIAL_FILTERS);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<NonNullable<TrainingJobListParams['sort']>>('created_at');
  const [dir, setDir] = useState<'asc' | 'desc'>('desc');
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(() =>
    searchParams.get('jobId'),
  );

  const params: TrainingJobListParams = {
    experiment_id: filters.experimentId || undefined,
    status: (filters.status || undefined) as TrainingJobListParams['status'],
    sort,
    dir,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };
  const jobs = useTrainingJobs(params);
  const experiments = useQuery({
    queryKey: ['experiments', 'select-options'],
    queryFn: () => fetchExperiments({ limit: 200, sort: 'updated_at', dir: 'desc' }),
  });

  const handleFiltersChange = (next: TrainingJobFiltersValue) => {
    setFilters(next);
    setPage(1);
  };

  const handleSortChange = (nextSort: typeof sort, nextDir: typeof dir) => {
    setSort(nextSort);
    setDir(nextDir);
    setPage(1);
  };

  return (
    <Stack spacing={2}>
      <Section
        title="Training Jobs"
        subtitle="Register and monitor placeholder training runs against an experiment"
        action={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New Training Job
          </Button>
        }
      >
        <Stack spacing={1.5}>
          <TrainingJobFiltersBar
            value={filters}
            onChange={handleFiltersChange}
            statuses={jobs.data?.statuses ?? []}
            experiments={experiments.data?.experiments ?? []}
          />
          {jobs.isError ? (
            <Alert
              severity="error"
              role="alert"
              action={<Button onClick={() => jobs.refetch()}>Retry</Button>}
            >
              {jobs.error instanceof Error ? jobs.error.message : 'Could not load training jobs.'}
            </Alert>
          ) : null}
          <TrainingJobsTable
            data={jobs.data}
            isLoading={jobs.isLoading}
            page={page}
            limit={PAGE_SIZE}
            sort={sort}
            dir={dir}
            onPageChange={setPage}
            onSortChange={handleSortChange}
            onSelect={(job: TrainingJobSummary) => setSelectedJobId(job.id)}
            hasExperiments={experiments.isLoading || (experiments.data?.total ?? 0) > 0}
          />
        </Stack>
      </Section>

      <CreateTrainingJobDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(id) => {
          setCreateOpen(false);
          setSelectedJobId(id);
        }}
      />

      <TrainingJobDetailDialog jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
    </Stack>
  );
}
