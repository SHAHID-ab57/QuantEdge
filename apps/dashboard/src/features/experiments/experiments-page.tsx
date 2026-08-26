'use client';

import AddIcon from '@mui/icons-material/Add';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Section } from '@/components/section';
import type { ExperimentListParams } from '@/lib/api/experiments';
import { CreateExperimentDialog } from './components/create-experiment-dialog';
import {
  ExperimentFiltersBar,
  type ExperimentFiltersValue,
} from './components/experiment-filters-bar';
import { ExperimentsTable } from './components/experiments-table';
import { useExperiments } from './hooks/use-experiments-data';

const PAGE_SIZE = 20;

const INITIAL_FILTERS: ExperimentFiltersValue = { search: '', status: '', tag: '' };

/**
 * The Experiment Management System's registry: search, filter, and sort
 * every recorded experiment, then open one to see its full detail. See
 * `ARCHITECTURE.md` § "Experiment Management System" for the backend this
 * page is a thin view over — every field here is exactly what
 * `GET /experiments` already returns, nothing computed client-side.
 */
export function ExperimentsPage() {
  const router = useRouter();
  const [filters, setFilters] = useState<ExperimentFiltersValue>(INITIAL_FILTERS);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<NonNullable<ExperimentListParams['sort']>>('created_at');
  const [dir, setDir] = useState<'asc' | 'desc'>('desc');
  const [createOpen, setCreateOpen] = useState(false);

  const params: ExperimentListParams = {
    q: filters.search || undefined,
    status: (filters.status || undefined) as ExperimentListParams['status'],
    tag: filters.tag || undefined,
    sort,
    dir,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };
  const experiments = useExperiments(params);

  const handleFiltersChange = (next: ExperimentFiltersValue) => {
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
        title="Experiments"
        subtitle="Every recorded attempt at building a model over a versioned ML dataset"
        action={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New Experiment
          </Button>
        }
      >
        <Stack spacing={1.5}>
          <ExperimentFiltersBar
            value={filters}
            onChange={handleFiltersChange}
            statuses={experiments.data?.statuses ?? []}
          />
          {experiments.isError ? (
            <Alert
              severity="error"
              role="alert"
              action={<Button onClick={() => experiments.refetch()}>Retry</Button>}
            >
              {experiments.error instanceof Error
                ? experiments.error.message
                : 'Could not load experiments.'}
            </Alert>
          ) : null}
          <ExperimentsTable
            data={experiments.data}
            isLoading={experiments.isLoading}
            page={page}
            limit={PAGE_SIZE}
            sort={sort}
            dir={dir}
            onPageChange={setPage}
            onSortChange={handleSortChange}
          />
        </Stack>
      </Section>

      <CreateExperimentDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(id) => {
          setCreateOpen(false);
          router.push(`/experiments/${id}`);
        }}
      />
    </Stack>
  );
}
