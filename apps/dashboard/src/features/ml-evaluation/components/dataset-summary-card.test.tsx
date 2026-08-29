import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { BenchmarkCandidate } from '@/types/api/evaluation';
import { DatasetSummaryCard } from './dataset-summary-card';

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
};

afterEach(() => cleanup());

describe('DatasetSummaryCard', () => {
  it('renders every field from the candidate', () => {
    render(
      <ThemeProvider theme={theme}>
        <DatasetSummaryCard candidate={CANDIDATE} />
      </ThemeProvider>,
    );
    expect(screen.getByText('ds-1')).toBeInTheDocument();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('1h')).toBeInTheDocument();
    expect(screen.getByText('200 rows')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('next_direction')).toBeInTheDocument();
  });

  it('shows a placeholder for a missing field rather than crashing', () => {
    render(
      <ThemeProvider theme={theme}>
        <DatasetSummaryCard
          candidate={{
            ...CANDIDATE,
            symbol: null,
            timeframe: null,
            feature_count: null,
            sample_count: null,
          }}
        />
      </ThemeProvider>,
    );
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
