import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { BenchmarkResponse } from '@/types/api/evaluation';
import { BenchmarkExportMenu } from './benchmark-export-menu';

const RESPONSE: BenchmarkResponse = {
  candidates: [
    {
      training_job_id: 'job-a',
      experiment_id: 'exp-1',
      experiment_name: 'Experiment A',
      model_type: 'logistic_regression',
      model_kind: 'classification',
      dataset_version: 'ds-1',
      target_column: 'next_direction',
      completed_at: '2026-01-01T00:00:00Z',
      metrics: { accuracy: 0.8 },
    },
  ],
  best_by_metric: [],
};

beforeAll(() => {
  // jsdom has no real object URL / anchor-click download support.
  Object.defineProperty(URL, 'createObjectURL', {
    value: vi.fn(() => 'blob:mock'),
    writable: true,
  });
  Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), writable: true });
});

afterEach(() => cleanup());

describe('BenchmarkExportMenu', () => {
  it('offers CSV and JSON export options', () => {
    render(
      <ThemeProvider theme={theme}>
        <BenchmarkExportMenu response={RESPONSE} datasetVersion="ds-1" />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Export' }));
    expect(screen.getByRole('menuitem', { name: 'Export CSV' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Export JSON' })).toBeInTheDocument();
  });

  it('triggers a download when an export option is clicked', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(
      <ThemeProvider theme={theme}>
        <BenchmarkExportMenu response={RESPONSE} datasetVersion="ds-1" />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Export' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Export CSV' }));
    expect(clickSpy).toHaveBeenCalledTimes(1);
    clickSpy.mockRestore();
  });
});
