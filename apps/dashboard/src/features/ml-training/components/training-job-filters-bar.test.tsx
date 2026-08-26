import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { TrainingJobFiltersBar, type TrainingJobFiltersValue } from './training-job-filters-bar';

afterEach(() => cleanup());

const EXPERIMENTS = [
  { id: 'exp-1', name: 'Baseline' },
  { id: 'exp-2', name: 'LSTM Attempt' },
];

function renderBar(value: TrainingJobFiltersValue = { experimentId: '', status: '' }) {
  const onChange = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <TrainingJobFiltersBar
        value={value}
        onChange={onChange}
        statuses={['pending', 'running', 'completed']}
        experiments={EXPERIMENTS}
      />
    </ThemeProvider>,
  );
  return onChange;
}

describe('TrainingJobFiltersBar', () => {
  it('renders an experiment filter and a status filter', () => {
    renderBar();
    expect(screen.getByLabelText('Experiment')).toBeInTheDocument();
    expect(screen.getByLabelText('Status')).toBeInTheDocument();
  });

  it('offers every experiment as an option', () => {
    renderBar();
    fireEvent.mouseDown(screen.getByLabelText('Experiment'));
    expect(screen.getByRole('option', { name: 'Baseline' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'LSTM Attempt' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'All experiments' })).toBeInTheDocument();
  });

  it('selecting an experiment calls onChange with its id', () => {
    const onChange = renderBar();
    fireEvent.mouseDown(screen.getByLabelText('Experiment'));
    fireEvent.click(screen.getByRole('option', { name: 'Baseline' }));
    expect(onChange).toHaveBeenCalledWith({ experimentId: 'exp-1', status: '' });
  });

  it('offers every status as an option', () => {
    renderBar();
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    expect(screen.getByRole('option', { name: 'Pending' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Running' })).toBeInTheDocument();
  });

  it('selecting a status calls onChange with that status', () => {
    const onChange = renderBar();
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    fireEvent.click(screen.getByRole('option', { name: 'Completed' }));
    expect(onChange).toHaveBeenCalledWith({ experimentId: '', status: 'completed' });
  });
});
