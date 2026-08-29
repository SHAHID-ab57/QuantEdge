import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { MetricSelector } from './metric-selector';

afterEach(() => cleanup());

describe('MetricSelector', () => {
  it('offers every given metric plus a None option', () => {
    render(
      <ThemeProvider theme={theme}>
        <MetricSelector metricNames={['accuracy', 'f1']} value={null} onChange={vi.fn()} />
      </ThemeProvider>,
    );
    fireEvent.mouseDown(screen.getByLabelText('Rank by metric'));
    expect(screen.getByRole('option', { name: 'None (most recent first)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'accuracy' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'f1' })).toBeInTheDocument();
  });

  it('calls onChange with the selected metric name', () => {
    const onChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <MetricSelector metricNames={['accuracy', 'f1']} value={null} onChange={onChange} />
      </ThemeProvider>,
    );
    fireEvent.mouseDown(screen.getByLabelText('Rank by metric'));
    fireEvent.click(screen.getByRole('option', { name: 'f1' }));
    expect(onChange).toHaveBeenCalledWith('f1');
  });

  it('calls onChange with null when None is selected', () => {
    const onChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <MetricSelector metricNames={['accuracy']} value="accuracy" onChange={onChange} />
      </ThemeProvider>,
    );
    fireEvent.mouseDown(screen.getByLabelText('Rank by metric'));
    fireEvent.click(screen.getByRole('option', { name: 'None (most recent first)' }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
