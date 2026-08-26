import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { ExperimentFiltersBar, type ExperimentFiltersValue } from './experiment-filters-bar';

afterEach(() => cleanup());

function renderBar(value: ExperimentFiltersValue = { search: '', status: '', tag: '' }) {
  const onChange = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <ExperimentFiltersBar value={value} onChange={onChange} statuses={['draft', 'running']} />
    </ThemeProvider>,
  );
  return onChange;
}

describe('ExperimentFiltersBar', () => {
  it('renders a search box, status filter, and tag filter', () => {
    renderBar();
    expect(screen.getByLabelText('Search experiments')).toBeInTheDocument();
    expect(screen.getByLabelText('Status')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter by tag')).toBeInTheDocument();
  });

  it('calls onChange with the updated search text', () => {
    const onChange = renderBar();
    fireEvent.change(screen.getByLabelText('Search experiments'), {
      target: { value: 'baseline' },
    });
    expect(onChange).toHaveBeenCalledWith({ search: 'baseline', status: '', tag: '' });
  });

  it('calls onChange with the updated tag', () => {
    const onChange = renderBar();
    fireEvent.change(screen.getByLabelText('Filter by tag'), { target: { value: 'sma' } });
    expect(onChange).toHaveBeenCalledWith({ search: '', status: '', tag: 'sma' });
  });

  it('offers every status as a select option', () => {
    renderBar();
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    expect(screen.getByRole('option', { name: 'Draft' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Running' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'All statuses' })).toBeInTheDocument();
  });

  it('selecting a status calls onChange with that status', () => {
    const onChange = renderBar();
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    fireEvent.click(screen.getByRole('option', { name: 'Running' }));
    expect(onChange).toHaveBeenCalledWith({ search: '', status: 'running', tag: '' });
  });

  it('selecting "All statuses" clears the status filter', () => {
    const onChange = renderBar({ search: '', status: 'running', tag: '' });
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    fireEvent.click(screen.getByRole('option', { name: 'All statuses' }));
    expect(onChange).toHaveBeenCalledWith({ search: '', status: '', tag: '' });
  });
});
