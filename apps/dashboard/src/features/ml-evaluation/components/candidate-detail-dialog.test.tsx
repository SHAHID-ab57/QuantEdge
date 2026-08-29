import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { BenchmarkCandidate } from '@/types/api/evaluation';
import { CandidateDetailDialog } from './candidate-detail-dialog';

const CANDIDATE: BenchmarkCandidate = {
  training_job_id: 'job-a',
  experiment_id: 'exp-1',
  experiment_name: 'Experiment A',
  model_type: 'logistic_regression',
  model_kind: 'classification',
  dataset_version: 'ds-1',
  target_column: 'next_direction',
  completed_at: '2026-01-01T00:00:00Z',
  metrics: { accuracy: 0.8 },
  symbol: 'ETHUSD',
  timeframe: '1h',
  feature_count: 5,
  sample_count: 200,
  model_artifact_url: '/api/v1/training-jobs/job-a/artifacts/model_joblib',
  report: {
    classes: ['up', 'down'],
    confusion_matrix: [
      [1, 0],
      [0, 1],
    ],
  },
};

afterEach(() => cleanup());

describe('CandidateDetailDialog', () => {
  it('renders nothing when no candidate is given', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <CandidateDetailDialog candidate={null} onClose={vi.fn()} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the model type, experiment name, deep links, and the dataset summary', () => {
    render(
      <ThemeProvider theme={theme}>
        <CandidateDetailDialog candidate={CANDIDATE} onClose={vi.fn()} />
      </ThemeProvider>,
    );
    expect(screen.getByText('logistic_regression')).toBeInTheDocument();
    expect(screen.getByText('Experiment A')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open experiment/i })).toHaveAttribute(
      'href',
      '/experiments/exp-1',
    );
    expect(screen.getByRole('link', { name: /open training job/i })).toHaveAttribute(
      'href',
      '/ml/training?jobId=job-a',
    );
    expect(screen.getByRole('link', { name: /download model artifact/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/v1/training-jobs/job-a/artifacts/model_joblib'),
    );
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
  });

  it('omits the artifact link when none was recorded', () => {
    render(
      <ThemeProvider theme={theme}>
        <CandidateDetailDialog
          candidate={{ ...CANDIDATE, model_artifact_url: null }}
          onClose={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(
      screen.queryByRole('link', { name: /download model artifact/i }),
    ).not.toBeInTheDocument();
  });
});
