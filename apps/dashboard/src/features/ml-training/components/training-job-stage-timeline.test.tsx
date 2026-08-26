import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { TrainingJobStageTimeline } from './training-job-stage-timeline';

afterEach(() => cleanup());

function renderTimeline(
  status: Parameters<typeof TrainingJobStageTimeline>[0]['status'],
  currentStage: Parameters<typeof TrainingJobStageTimeline>[0]['currentStage'],
) {
  render(
    <ThemeProvider theme={theme}>
      <TrainingJobStageTimeline status={status} currentStage={currentStage} />
    </ThemeProvider>,
  );
}

const ALL_LABELS = [
  'Pending',
  'Dataset Validation',
  'Dataset Loaded',
  'Model Initialized',
  'Training',
  'Saving Results',
  'Experiment Updated',
  'Completed',
];

describe('TrainingJobStageTimeline', () => {
  it('always renders every one of the eight steps', () => {
    renderTimeline('pending', null);
    for (const label of ALL_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('marks the current stage as the active step while running', () => {
    renderTimeline('running', 'execute_training');
    const step = screen.getByText('Training');
    expect(step).toHaveStyle({ fontWeight: '700' });
  });

  it('marks every stage done once completed', () => {
    renderTimeline('completed', 'update_experiment');
    expect(screen.getByText('Completed')).toBeInTheDocument();
    // No step should carry the "active" bold weight once the job is done.
    for (const label of ALL_LABELS) {
      expect(screen.getByText(label)).not.toHaveStyle({ fontWeight: '700' });
    }
  });

  it('exposes the active step via aria-current', () => {
    renderTimeline('running', 'load_dataset');
    const items = screen.getAllByRole('listitem');
    const active = items.find((item) => item.getAttribute('aria-current') === 'step');
    expect(active).toBeDefined();
    expect(active).toHaveTextContent('Dataset Loaded');
  });

  it('has no active step for a pending job', () => {
    renderTimeline('pending', null);
    const items = screen.getAllByRole('listitem');
    expect(items.some((item) => item.getAttribute('aria-current') === 'step')).toBe(false);
  });

  it('has no active step once failed — the failing stage is marked, not active', () => {
    renderTimeline('failed', 'initialize_model');
    const items = screen.getAllByRole('listitem');
    expect(items.some((item) => item.getAttribute('aria-current') === 'step')).toBe(false);
  });
});
