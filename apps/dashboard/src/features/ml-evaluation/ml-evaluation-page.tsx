'use client';

import LeaderboardIcon from '@mui/icons-material/Leaderboard';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ConfirmActionDialog } from '@/components/confirm-action-dialog';
import { EmptyStateNotice } from '@/components/empty-state-notice';
import { Section } from '@/components/section';
import { fetchExperiments } from '@/lib/api/experiments';
import type { BenchmarkCandidate, BenchmarkRunSummary } from '@/types/api/evaluation';
import { BenchmarkComparisonTable } from './components/benchmark-comparison-table';
import { BenchmarkExportMenu } from './components/benchmark-export-menu';
import {
  BenchmarkFiltersBar,
  type BenchmarkFiltersValue,
} from './components/benchmark-filters-bar';
import { BenchmarkHistoryTable } from './components/benchmark-history-table';
import { BestModelSummary } from './components/best-model-summary';
import { CandidateDetailDialog } from './components/candidate-detail-dialog';
import { MetricCatalogPanel } from './components/metric-catalog-panel';
import { MetricComparisonChart } from './components/metric-comparison-chart';
import { MetricSelector } from './components/metric-selector';
import {
  useBenchmark,
  useBenchmarkHistory,
  useBenchmarkRun,
  useDeleteBenchmarkRun,
  useMetricCatalog,
} from './hooks/use-evaluation-data';

const INITIAL_FILTERS: BenchmarkFiltersValue = {
  datasetVersion: '',
  targetColumn: '',
  experimentIds: [],
};

const HISTORY_PAGE_SIZE = 10;

/**
 * The Model Evaluation & Benchmarking Engine's comparison surface: pick a
 * dataset version, target column, and/or a set of experiments, and compare
 * every completed training job matching that — a read-only view over
 * metrics already recorded during training (`app/evaluation/`), never a
 * re-computation. Answers "which model performs best" directly (the
 * `BestModelSummary` cards and the metric-driven Rank column), with the
 * full comparison table, per-metric charts, CSV/JSON export, per-candidate
 * detail (confusion matrix, ROC/PR curves — reusing `EvaluationSummary`
 * verbatim), deep links to the Experiment/Training Job/Model Artifact
 * behind each row, Benchmark History (every past comparison, reopenable),
 * and the registered metric catalogue as a standing reference.
 */
export function MLEvaluationPage() {
  const [filters, setFilters] = useState<BenchmarkFiltersValue>(INITIAL_FILTERS);
  const [rankMetric, setRankMetric] = useState<string | null>(null);
  const [detailCandidate, setDetailCandidate] = useState<BenchmarkCandidate | null>(null);
  const [reopenedRunId, setReopenedRunId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [deletingRun, setDeletingRun] = useState<BenchmarkRunSummary | null>(null);

  const experiments = useQuery({
    queryKey: ['experiments', 'select-options'],
    queryFn: () => fetchExperiments({ limit: 200, sort: 'updated_at', dir: 'desc' }),
  });
  const metricCatalog = useMetricCatalog();
  const benchmark = useBenchmark();
  const reopenedRun = useBenchmarkRun(reopenedRunId);
  const history = useBenchmarkHistory({
    limit: HISTORY_PAGE_SIZE,
    offset: (historyPage - 1) * HISTORY_PAGE_SIZE,
  });
  const deleteRun = useDeleteBenchmarkRun();

  // Reopening a past run restores the exact filters it was made with, so
  // the filter bar reflects what produced the comparison now on screen.
  useEffect(() => {
    if (!reopenedRun.data) return;
    const { request } = reopenedRun.data;
    setFilters({
      datasetVersion: request.dataset_version ?? '',
      targetColumn: request.target_column ?? '',
      experimentIds: request.experiment_ids ?? [],
    });
  }, [reopenedRun.data]);

  const activeResult = reopenedRunId ? reopenedRun.data?.response : benchmark.data;

  const datasetVersionOptions = useMemo(() => {
    const versions = new Set<string>();
    for (const experiment of experiments.data?.experiments ?? []) {
      if (experiment.dataset_version) versions.add(experiment.dataset_version);
    }
    return Array.from(versions).sort();
  }, [experiments.data]);

  const metricNames = useMemo(() => {
    const names = new Set<string>();
    for (const candidate of activeResult?.candidates ?? []) {
      for (const name of Object.keys(candidate.metrics)) names.add(name);
    }
    return Array.from(names).sort();
  }, [activeResult]);

  const handleSubmit = useCallback(() => {
    setReopenedRunId(null);
    benchmark.mutate({
      dataset_version: filters.datasetVersion.trim() || undefined,
      target_column: filters.targetColumn.trim() || undefined,
      experiment_ids: filters.experimentIds.length > 0 ? filters.experimentIds : undefined,
    });
  }, [benchmark, filters]);

  const handleReopen = (run: BenchmarkRunSummary) => setReopenedRunId(run.id);

  const handleConfirmDelete = () => {
    if (!deletingRun) return;
    deleteRun.mutate(deletingRun.id, {
      onSuccess: () => {
        setDeletingRun(null);
        if (reopenedRunId === deletingRun.id) setReopenedRunId(null);
      },
    });
  };

  const isError = reopenedRunId ? reopenedRun.isError : benchmark.isError;
  const errorMessage = reopenedRunId
    ? (reopenedRun.error?.message ?? 'Could not reopen this benchmark run.')
    : (benchmark.error?.message ?? '');

  return (
    <Stack spacing={2}>
      <Section
        title="Benchmark Comparison"
        subtitle="Compare completed training jobs by dataset, target, or experiment"
      >
        <Stack spacing={2}>
          <BenchmarkFiltersBar
            value={filters}
            onChange={setFilters}
            onSubmit={handleSubmit}
            experiments={experiments.data?.experiments ?? []}
            experimentsLoading={experiments.isLoading}
            datasetVersionOptions={datasetVersionOptions}
            submitting={benchmark.isPending}
          />

          {isError ? (
            <Alert
              severity={errorMessage.includes('No completed') ? 'info' : 'error'}
              role="alert"
              action={<Button onClick={handleSubmit}>Retry</Button>}
            >
              {errorMessage}
            </Alert>
          ) : null}

          {!activeResult && !isError ? (
            <EmptyStateNotice
              icon={<LeaderboardIcon fontSize="small" color="disabled" />}
              title="No comparison run yet"
              description="Choose a dataset version, target column, and/or experiments above, then select Compare."
            />
          ) : null}

          {activeResult ? (
            <Stack spacing={2}>
              {reopenedRunId ? (
                <Alert severity="info" onClose={() => setReopenedRunId(null)}>
                  Viewing a reopened comparison from Benchmark History.
                </Alert>
              ) : null}
              <Stack
                direction="row"
                spacing={2}
                alignItems="center"
                justifyContent="space-between"
                flexWrap="wrap"
                useFlexGap
              >
                <MetricSelector
                  metricNames={metricNames}
                  value={rankMetric}
                  onChange={setRankMetric}
                />
                <BenchmarkExportMenu
                  response={activeResult}
                  datasetVersion={filters.datasetVersion || null}
                />
              </Stack>
              <BestModelSummary bestByMetric={activeResult.best_by_metric} />
              <BenchmarkComparisonTable
                candidates={activeResult.candidates}
                bestByMetric={activeResult.best_by_metric}
                rankMetric={rankMetric}
                onOpenDetail={setDetailCandidate}
              />
              <Stack spacing={1.5}>
                <Typography variant="caption" color="text.secondary">
                  Metric charts — one bar per model that recorded this metric
                </Typography>
                <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
                  {metricNames.map((name) => (
                    <MetricComparisonChart
                      key={name}
                      metricName={name}
                      candidates={activeResult.candidates}
                    />
                  ))}
                </Stack>
              </Stack>
            </Stack>
          ) : null}
        </Stack>
      </Section>

      <Section
        title="Benchmark History"
        subtitle="Every past comparison — reopen one to see it again, exactly as it was"
      >
        <BenchmarkHistoryTable
          data={history.data}
          isLoading={history.isLoading}
          page={historyPage}
          limit={HISTORY_PAGE_SIZE}
          onPageChange={setHistoryPage}
          onReopen={handleReopen}
          onDelete={setDeletingRun}
        />
      </Section>

      <Section
        title="Available Metrics"
        subtitle="Every metric this engine can compute — new metrics register here automatically"
      >
        {metricCatalog.isError ? (
          <Alert severity="error" role="alert">
            Could not load the metric catalogue.
          </Alert>
        ) : (
          <MetricCatalogPanel metrics={metricCatalog.data?.metrics ?? []} />
        )}
      </Section>

      <CandidateDetailDialog candidate={detailCandidate} onClose={() => setDetailCandidate(null)} />

      <ConfirmActionDialog
        open={deletingRun !== null}
        title="Remove this benchmark run?"
        description="This only removes the persisted comparison from Benchmark History — the underlying training jobs are untouched."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        busy={deleteRun.isPending}
        onCancel={() => setDeletingRun(null)}
        onConfirm={handleConfirmDelete}
      />
    </Stack>
  );
}
