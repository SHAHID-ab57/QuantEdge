import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { Experiment } from '@/types/api/experiments';
import { TrainingSummaryPanel } from './training-summary-panel';

afterEach(() => cleanup());

function experiment(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: 'exp-1',
    name: 'Baseline SMA',
    dataset_version: 'ds-abc',
    feature_set: [
      { feature: 'sma', params: {} },
      { feature: 'ema', params: {} },
    ],
    target_config: [{ target: 'next_close', params: { horizon: '3' } }],
    split_config: { train: 0.7, validation: 0.15, test: 0.15 },
    model_type: 'xgboost',
    status: 'draft',
    notes: null,
    tags: [],
    metrics: [],
    artifacts: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderPanel(props: Partial<Parameters<typeof TrainingSummaryPanel>[0]> = {}) {
  render(
    <ThemeProvider theme={theme}>
      <TrainingSummaryPanel experiment={null} datasetVersion="" modelLabel={null} {...props} />
    </ThemeProvider>,
  );
}

describe('TrainingSummaryPanel', () => {
  it('shows warning chips when nothing is selected yet', () => {
    renderPanel();
    expect(screen.getAllByText('Not selected').length).toBe(2); // Experiment + Model
    expect(screen.getByText('Missing')).toBeInTheDocument(); // Dataset version
    expect(screen.getAllByText('Select an experiment').length).toBeGreaterThan(0);
  });

  it('shows the experiment name, target, split, and feature count once selected', () => {
    renderPanel({ experiment: experiment(), datasetVersion: 'ds-abc', modelLabel: 'XGBoost' });
    expect(screen.getByText('Baseline SMA')).toBeInTheDocument();
    expect(screen.getByText('ds-abc')).toBeInTheDocument();
    expect(screen.getByText('next_close')).toBeInTheDocument();
    expect(screen.getByText('XGBoost')).toBeInTheDocument();
    expect(screen.getByText('70% / 15% / 15%')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows the recorded prediction horizon', () => {
    renderPanel({ experiment: experiment(), datasetVersion: 'ds-abc', modelLabel: null });
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('reports the prediction horizon as not recorded when absent', () => {
    renderPanel({
      experiment: experiment({ target_config: [{ target: 'next_close', params: {} }] }),
      datasetVersion: 'ds-abc',
      modelLabel: null,
    });
    expect(screen.getByText('Not recorded')).toBeInTheDocument();
  });

  it('always reports the dataset size as not tracked', () => {
    renderPanel({ experiment: experiment(), datasetVersion: 'ds-abc', modelLabel: null });
    expect(screen.getByText('Not tracked')).toBeInTheDocument();
  });

  it('always reports the validation status as unknown', () => {
    renderPanel({ experiment: experiment(), datasetVersion: 'ds-abc', modelLabel: null });
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('shows a missing-model chip until a model is selected', () => {
    renderPanel({ experiment: experiment(), datasetVersion: 'ds-abc', modelLabel: null });
    expect(screen.getAllByText('Not selected').length).toBeGreaterThan(0);
  });
});
