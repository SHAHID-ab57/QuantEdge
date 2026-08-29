import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { ExperimentSummary } from '@/types/api/experiments';
import { BenchmarkFiltersBar, type BenchmarkFiltersValue } from './benchmark-filters-bar';

afterEach(() => cleanup());

const EXPERIMENTS: ExperimentSummary[] = [
  {
    id: 'exp-1',
    name: 'Baseline',
    dataset_version: 'ds-1',
    model_type: null,
    status: 'completed',
    tags: [],
    metric_count: 0,
    artifact_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

function renderBar(
  value: BenchmarkFiltersValue = { datasetVersion: '', targetColumn: '', experimentIds: [] },
) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <BenchmarkFiltersBar
        value={value}
        onChange={onChange}
        onSubmit={onSubmit}
        experiments={EXPERIMENTS}
        experimentsLoading={false}
        datasetVersionOptions={['ds-1', 'ds-2']}
        submitting={false}
      />
    </ThemeProvider>,
  );
  return { onChange, onSubmit };
}

describe('BenchmarkFiltersBar', () => {
  it('renders every filter field', () => {
    renderBar();
    expect(screen.getByLabelText('Dataset version')).toBeInTheDocument();
    expect(screen.getByLabelText('Target column')).toBeInTheDocument();
    expect(screen.getByLabelText('Experiments')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare' })).toBeInTheDocument();
  });

  it('disables Compare when nothing is given', () => {
    renderBar();
    expect(screen.getByRole('button', { name: 'Compare' })).toBeDisabled();
  });

  it('enables Compare once a target column is typed', () => {
    renderBar({ datasetVersion: '', targetColumn: 'next_direction', experimentIds: [] });
    expect(screen.getByRole('button', { name: 'Compare' })).toBeEnabled();
  });

  it('typing a target column calls onChange', () => {
    const { onChange } = renderBar();
    fireEvent.change(screen.getByLabelText('Target column'), { target: { value: 'next_close' } });
    expect(onChange).toHaveBeenCalledWith({
      datasetVersion: '',
      targetColumn: 'next_close',
      experimentIds: [],
    });
  });

  it('calls onSubmit when Compare is clicked and something is given', () => {
    const { onSubmit } = renderBar({
      datasetVersion: 'ds-1',
      targetColumn: '',
      experimentIds: [],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));
    expect(onSubmit).toHaveBeenCalled();
  });

  it('selecting an experiment adds its id to experimentIds', () => {
    const { onChange } = renderBar();
    fireEvent.mouseDown(screen.getByLabelText('Experiments'));
    fireEvent.click(screen.getByRole('option', { name: 'Baseline' }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ experimentIds: ['exp-1'] }));
  });
});
