import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api/errors';
import * as evaluationApi from '@/lib/api/evaluation';
import * as experimentsApi from '@/lib/api/experiments';
import type { ExperimentListResponse } from '@/types/api/experiments';
import type { BenchmarkResponse, MetricCatalogResponse } from '@/types/api/evaluation';
import { MLEvaluationPage } from './ml-evaluation-page';

vi.mock('@/lib/api/evaluation', () => ({
  fetchMetricCatalog: vi.fn(),
  runBenchmark: vi.fn(),
}));

vi.mock('@/lib/api/experiments', () => ({
  fetchExperiments: vi.fn(),
}));

const mockedEvaluationApi = vi.mocked(evaluationApi);
const mockedExperimentsApi = vi.mocked(experimentsApi);

function experimentListResponse(
  overrides: Partial<ExperimentListResponse> = {},
): ExperimentListResponse {
  return {
    experiments: [
      {
        id: 'exp-1',
        name: 'Baseline',
        dataset_version: 'ds-1',
        model_type: 'logistic_regression',
        status: 'completed',
        tags: [],
        metric_count: 2,
        artifact_count: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    total: 1,
    limit: 200,
    offset: 0,
    statuses: ['draft', 'running', 'completed', 'failed', 'archived'],
    artifact_types: ['dataset_export', 'model_checkpoint', 'report', 'plot', 'other'],
    ...overrides,
  };
}

function metricCatalog(): MetricCatalogResponse {
  return {
    metrics: [
      {
        name: 'accuracy',
        label: 'Accuracy',
        description: 'Overall fraction correct.',
        category: 'classification',
        higher_is_better: true,
        requires_probabilities: false,
        version: '1.0.0',
      },
      {
        name: 'rmse',
        label: 'RMSE',
        description: 'Root mean squared error.',
        category: 'regression',
        higher_is_better: false,
        requires_probabilities: false,
        version: '1.0.0',
      },
    ],
  };
}

function benchmarkResponse(overrides: Partial<BenchmarkResponse> = {}): BenchmarkResponse {
  return {
    candidates: [
      {
        training_job_id: 'job-a',
        experiment_id: 'exp-1',
        experiment_name: 'Baseline',
        model_type: 'logistic_regression',
        model_kind: 'classification',
        dataset_version: 'ds-1',
        target_column: 'next_direction',
        completed_at: '2026-01-01T00:00:00Z',
        metrics: { accuracy: 0.9 },
      },
    ],
    best_by_metric: [
      {
        metric: 'accuracy',
        training_job_id: 'job-a',
        model_type: 'logistic_regression',
        value: 0.9,
        higher_is_better: true,
      },
    ],
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MLEvaluationPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedEvaluationApi.fetchMetricCatalog.mockResolvedValue(metricCatalog());
  mockedExperimentsApi.fetchExperiments.mockResolvedValue(experimentListResponse());
});

afterEach(() => cleanup());

describe('MLEvaluationPage', () => {
  it('shows an empty-state notice before any comparison is run', async () => {
    renderPage();
    expect(await screen.findByText('No comparison run yet')).toBeInTheDocument();
  });

  it('renders the metric catalogue', async () => {
    renderPage();
    expect(screen.getByText('Classification metrics')).toBeInTheDocument();
    expect(screen.getByText('Regression metrics')).toBeInTheDocument();
    expect(await screen.findByText('Accuracy')).toBeInTheDocument();
  });

  it('runs a benchmark and renders the comparison table and best-model summary', async () => {
    mockedEvaluationApi.runBenchmark.mockResolvedValue(benchmarkResponse());
    renderPage();
    await screen.findByText('No comparison run yet');

    fireEvent.change(screen.getByLabelText('Target column'), {
      target: { value: 'next_direction' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));

    await waitFor(() =>
      expect(mockedEvaluationApi.runBenchmark).toHaveBeenCalledWith(
        expect.objectContaining({ target_column: 'next_direction' }),
      ),
    );
    expect((await screen.findAllByText('logistic_regression')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('accuracy').length).toBeGreaterThan(0);
  });

  it('shows an informational message when nothing matched the benchmark', async () => {
    mockedEvaluationApi.runBenchmark.mockRejectedValue(
      new ApiError(
        404,
        'empty_benchmark',
        'No completed training jobs matched this benchmark request',
      ),
    );
    renderPage();
    await screen.findByText('No comparison run yet');

    fireEvent.change(screen.getByLabelText('Target column'), { target: { value: 'next_close' } });
    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));

    expect(
      await screen.findByText('No completed training jobs matched this benchmark request'),
    ).toBeInTheDocument();
  });
});
