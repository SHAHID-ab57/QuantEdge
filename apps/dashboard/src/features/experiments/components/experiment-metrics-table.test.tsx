import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { Metric } from '@/types/api/experiments';
import { ExperimentMetricsTable } from './experiment-metrics-table';

afterEach(() => cleanup());

function metric(overrides: Partial<Metric> = {}): Metric {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    name: 'accuracy',
    value: 0.87,
    unit: 'ratio',
    recorded_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderTable(metrics: Metric[] = []) {
  const onAdd = vi.fn();
  const onDelete = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <ExperimentMetricsTable metrics={metrics} onAdd={onAdd} onDelete={onDelete} />
    </ThemeProvider>,
  );
  return { onAdd, onDelete };
}

describe('ExperimentMetricsTable — empty state', () => {
  it('shows a placeholder when there are no metrics', () => {
    renderTable([]);
    expect(screen.getByText('No metrics recorded yet.')).toBeInTheDocument();
  });
});

describe('ExperimentMetricsTable — display', () => {
  it('renders each metric’s name, value, and unit', () => {
    renderTable([metric()]);
    expect(screen.getByText('accuracy')).toBeInTheDocument();
    expect(screen.getByText('0.87')).toBeInTheDocument();
    expect(screen.getByText('ratio')).toBeInTheDocument();
  });

  it('renders an em dash for a metric with no unit', () => {
    renderTable([metric({ unit: null })]);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

describe('ExperimentMetricsTable — adding a metric', () => {
  it('disables Add Metric until a name and a numeric value are entered', () => {
    renderTable([]);
    const button = screen.getByRole('button', { name: 'Add Metric' });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Metric name'), { target: { value: 'sharpe' } });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Metric value'), { target: { value: '1.5' } });
    expect(button).not.toBeDisabled();
  });

  it('calls onAdd with the entered name/value/unit and clears the form', () => {
    const { onAdd } = renderTable([]);
    fireEvent.change(screen.getByLabelText('Metric name'), { target: { value: 'sharpe' } });
    fireEvent.change(screen.getByLabelText('Metric value'), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText('Metric unit'), { target: { value: 'ratio' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Metric' }));

    expect(onAdd).toHaveBeenCalledWith({ name: 'sharpe', value: 1.5, unit: 'ratio' });
    expect(screen.getByLabelText('Metric name')).toHaveValue('');
  });

  it('sends null for an omitted unit', () => {
    const { onAdd } = renderTable([]);
    fireEvent.change(screen.getByLabelText('Metric name'), { target: { value: 'accuracy' } });
    fireEvent.change(screen.getByLabelText('Metric value'), { target: { value: '0.9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Metric' }));

    expect(onAdd).toHaveBeenCalledWith({ name: 'accuracy', value: 0.9, unit: null });
  });
});

describe('ExperimentMetricsTable — deleting a metric', () => {
  it('calls onDelete with the metric id', () => {
    const { onDelete } = renderTable([metric()]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete metric accuracy' }));
    expect(onDelete).toHaveBeenCalledWith('11111111-1111-4111-8111-111111111111');
  });
});
