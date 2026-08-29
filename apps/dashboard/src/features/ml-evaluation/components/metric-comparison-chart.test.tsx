import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { BenchmarkCandidate } from '@/types/api/evaluation';
import { MetricComparisonChart } from './metric-comparison-chart';

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
    metrics: { accuracy: 0.7 },
  },
  {
    training_job_id: 'job-b',
    experiment_id: 'exp-1',
    experiment_name: 'Experiment A',
    model_type: 'random_forest',
    model_kind: 'classification',
    dataset_version: 'ds-1',
    target_column: 'next_direction',
    completed_at: '2026-01-02T00:00:00Z',
    metrics: {},
  },
];

afterEach(() => cleanup());

describe('MetricComparisonChart', () => {
  it('renders a labeled bar per candidate that recorded the metric', () => {
    render(
      <ThemeProvider theme={theme}>
        <MetricComparisonChart metricName="accuracy" candidates={CANDIDATES} />
      </ThemeProvider>,
    );
    expect(
      screen.getByRole('img', { name: /accuracy comparison across 1 models/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('accuracy')).toBeInTheDocument();
  });

  it('renders nothing when no candidate recorded the metric', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <MetricComparisonChart metricName="roc_auc" candidates={CANDIDATES} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
