import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { BenchmarkBestEntry, BenchmarkCandidate } from '@/types/api/evaluation';
import { BenchmarkComparisonTable } from './benchmark-comparison-table';

const CANDIDATES: BenchmarkCandidate[] = [
  {
    training_job_id: 'job-a',
    experiment_id: 'exp-1',
    experiment_name: 'Experiment A',
    model_type: 'logistic_regression',
    model_kind: 'classification',
    dataset_version: 'ds-1',
    target_column: 'next_direction',
    completed_at: '2026-01-01T00:00:00Z',
    metrics: { accuracy: 0.7, f1: 0.65 },
    model_artifact_url: '/api/v1/training-jobs/job-a/artifacts/model_joblib',
  },
  {
    training_job_id: 'job-b',
    experiment_id: 'exp-1',
    experiment_name: 'Experiment A',
    model_type: 'logistic_regression',
    model_kind: 'classification',
    dataset_version: 'ds-1',
    target_column: 'next_direction',
    completed_at: '2026-01-02T00:00:00Z',
    metrics: { accuracy: 0.9, f1: 0.85 },
    model_artifact_url: '/api/v1/training-jobs/job-b/artifacts/model_joblib',
  },
];

const BEST: BenchmarkBestEntry[] = [
  {
    metric: 'accuracy',
    training_job_id: 'job-b',
    model_type: 'logistic_regression',
    value: 0.9,
    higher_is_better: true,
  },
  {
    metric: 'f1',
    training_job_id: 'job-b',
    model_type: 'logistic_regression',
    value: 0.85,
    higher_is_better: true,
  },
];

afterEach(() => cleanup());

function renderTable(overrides: Partial<Parameters<typeof BenchmarkComparisonTable>[0]> = {}) {
  const onOpenDetail = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <BenchmarkComparisonTable
        candidates={CANDIDATES}
        bestByMetric={BEST}
        rankMetric={null}
        onOpenDetail={onOpenDetail}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { onOpenDetail };
}

describe('BenchmarkComparisonTable', () => {
  it('renders one row per candidate with a column per metric', () => {
    renderTable();
    expect(screen.getAllByText('logistic_regression').length).toBe(2);
    expect(screen.getByText('0.7000')).toBeInTheDocument();
    expect(screen.getByText('0.9000')).toBeInTheDocument();
  });

  it('renders a placeholder cell for a metric missing on some candidates', () => {
    const partial: BenchmarkCandidate[] = [
      ...CANDIDATES,
      { ...CANDIDATES[0]!, training_job_id: 'job-c', metrics: { accuracy: 0.5 } },
    ];
    renderTable({ candidates: partial });
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('sorts rows by completed_at descending when no rank metric is chosen', () => {
    renderTable();
    const rows = screen.getAllByRole('row');
    // Row 0 is the header; row 1 should be the most-recently-completed job.
    expect(rows[1]?.textContent).toContain('0.9000');
  });

  it('ranks rows by the chosen metric, best first, with a Rank column', () => {
    renderTable({ rankMetric: 'accuracy' });
    expect(screen.getByText('Rank')).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(rows[1]?.textContent).toContain('0.9000');
    expect(rows[1]?.textContent).toContain('1');
    expect(rows[2]?.textContent).toContain('2');
  });

  it('ranks a lower-is-better metric ascending', () => {
    const candidates: BenchmarkCandidate[] = [
      { ...CANDIDATES[0]!, metrics: { rmse: 0.5 } },
      { ...CANDIDATES[1]!, metrics: { rmse: 0.2 } },
    ];
    const best: BenchmarkBestEntry[] = [
      {
        metric: 'rmse',
        training_job_id: 'job-b',
        model_type: 'logistic_regression',
        value: 0.2,
        higher_is_better: false,
      },
    ];
    renderTable({ candidates, bestByMetric: best, rankMetric: 'rmse' });
    const rows = screen.getAllByRole('row');
    expect(rows[1]?.textContent).toContain('0.2000');
  });

  it("calls onOpenDetail with the clicked row's own candidate", () => {
    const { onOpenDetail } = renderTable();
    // Default order is completed_at descending, so the first rendered row is job-b.
    screen.getAllByLabelText('View details for logistic_regression')[0]?.click();
    expect(onOpenDetail).toHaveBeenCalledWith(CANDIDATES[1]);
  });

  it('links every row to its experiment and training job', () => {
    renderTable();
    expect(screen.getAllByLabelText('Open experiment Experiment A').length).toBe(2);
    expect(screen.getByLabelText('Open training job job-a')).toHaveAttribute(
      'href',
      '/ml/training?jobId=job-a',
    );
  });

  it('links to the downloadable model artifact when one was recorded', () => {
    renderTable();
    expect(screen.getAllByLabelText('Download model artifact for logistic_regression').length).toBe(
      2,
    );
  });

  it('omits the artifact link when no artifact was recorded', () => {
    const candidates: BenchmarkCandidate[] = [{ ...CANDIDATES[0]!, model_artifact_url: null }];
    renderTable({ candidates });
    expect(
      screen.queryByLabelText('Download model artifact for logistic_regression'),
    ).not.toBeInTheDocument();
  });
});
