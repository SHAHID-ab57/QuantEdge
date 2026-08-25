import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import * as downloadFile from '@/lib/download-file';
import type { ValidationIssue, ValidationReport } from '@/types/api/dataset-validation';
import { ValidationReportPanel } from './validation-report-panel';

vi.mock('@/lib/download-file', () => ({ downloadBlob: vi.fn() }));

function issue(overrides: Partial<ValidationIssue> = {}): ValidationIssue {
  return {
    rule: 'duplicate_timestamps',
    category: 'data_quality',
    severity: 'error',
    code: 'duplicate_timestamps',
    message: 'timestamps repeat',
    column: null,
    row_index: null,
    count: 1,
    details: {},
    ...overrides,
  };
}

function report(issues: ValidationIssue[]): ValidationReport {
  return {
    dataset_id: 'abc',
    symbol: 'ETHUSD',
    timeframe: '1h',
    engine_version: '1.0.0',
    validated_at: '2026-01-01T02:03:04Z',
    passed: issues.every((entry) => entry.severity !== 'error'),
    rules_run: [],
    summary: { total_checks: issues.length, errors: 0, warnings: 0, info: 0 },
    categories: {},
    issues,
    rows: 1,
    columns: 1,
    duration_ms: 1,
  };
}

function renderPanel(issues: ValidationIssue[]) {
  return render(
    <ThemeProvider theme={theme}>
      <ValidationReportPanel report={report(issues)} />
    </ThemeProvider>,
  );
}

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: vi.fn(() => 'blob:mock'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ValidationReportPanel — empty states', () => {
  it('reports every check passed when there are no issues at all', () => {
    renderPanel([]);
    expect(screen.getByRole('status')).toHaveTextContent('every structural, data-quality');
  });

  it('reports no matches when filters exclude everything', () => {
    renderPanel([issue({ severity: 'error' })]);
    fireEvent.change(screen.getByRole('textbox', { name: 'Search issues' }), {
      target: { value: 'nonexistent' },
    });
    expect(screen.getByRole('status')).toHaveTextContent('No issues match the current filters.');
  });
});

describe('ValidationReportPanel — search', () => {
  it('filters issues by message text', () => {
    renderPanel([
      issue({ code: 'a', message: 'alpha problem' }),
      issue({ code: 'b', message: 'beta problem' }),
    ]);
    fireEvent.change(screen.getByRole('textbox', { name: 'Search issues' }), {
      target: { value: 'alpha' },
    });
    expect(screen.getByText('alpha problem')).toBeInTheDocument();
    expect(screen.queryByText('beta problem')).not.toBeInTheDocument();
  });

  it('filters by rule name', () => {
    renderPanel([
      issue({ rule: 'time_gaps', code: 'time_gaps', message: 'gap found' }),
      issue({ rule: 'nan_values', code: 'nan_values', message: 'nan found' }),
    ]);
    fireEvent.change(screen.getByRole('textbox', { name: 'Search issues' }), {
      target: { value: 'time_gaps' },
    });
    expect(screen.getByText('gap found')).toBeInTheDocument();
    expect(screen.queryByText('nan found')).not.toBeInTheDocument();
  });
});

describe('ValidationReportPanel — severity filter', () => {
  it('shows every severity by default', () => {
    renderPanel([
      issue({ severity: 'error', code: 'e', message: 'error message' }),
      issue({ severity: 'warning', code: 'w', message: 'warning message' }),
    ]);
    expect(screen.getByText('error message')).toBeInTheDocument();
    expect(screen.getByText('warning message')).toBeInTheDocument();
  });

  it('toggling a severity off hides its issues', () => {
    renderPanel([
      issue({ severity: 'error', code: 'e', message: 'error message' }),
      issue({ severity: 'warning', code: 'w', message: 'warning message' }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'error' }));
    expect(screen.queryByText('error message')).not.toBeInTheDocument();
    expect(screen.getByText('warning message')).toBeInTheDocument();
  });

  it('toggling it back on restores those issues', () => {
    renderPanel([issue({ severity: 'error', code: 'e', message: 'error message' })]);
    const errorChip = screen.getByRole('button', { name: 'error' });
    fireEvent.click(errorChip);
    fireEvent.click(errorChip);
    expect(screen.getByText('error message')).toBeInTheDocument();
  });
});

describe('ValidationReportPanel — category filter', () => {
  it('shows only issues in the selected category', () => {
    renderPanel([
      issue({ category: 'data_quality', code: 'dq', message: 'quality problem' }),
      issue({ category: 'time_series', code: 'ts', message: 'series problem' }),
    ]);
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Category' }));
    fireEvent.click(screen.getByRole('option', { name: 'Time-Series' }));
    expect(screen.getByText('series problem')).toBeInTheDocument();
    expect(screen.queryByText('quality problem')).not.toBeInTheDocument();
  });
});

describe('ValidationReportPanel — expand all / collapse all', () => {
  it('expands every row at once', () => {
    renderPanel([issue({ code: 'duplicate_timestamps' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Expand All' }));
    expect(screen.getByText(/Suggested fix:/)).toBeInTheDocument();
  });

  it('collapses every row at once', async () => {
    renderPanel([issue({ code: 'duplicate_timestamps' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Expand All' }));
    fireEvent.click(screen.getByRole('button', { name: 'Collapse All' }));
    await waitFor(() => {
      expect(screen.queryByText(/Suggested fix:/)).not.toBeInTheDocument();
    });
  });
});

describe('ValidationReportPanel — export issues', () => {
  it('exports only the currently-filtered issues', () => {
    renderPanel([
      issue({ severity: 'error', code: 'e', message: 'error message' }),
      issue({ severity: 'warning', code: 'w', message: 'warning message' }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'error' }));
    fireEvent.click(screen.getByRole('button', { name: 'Export filtered issues as JSON' }));

    const mocked = vi.mocked(downloadFile);
    expect(mocked.downloadBlob).toHaveBeenCalledTimes(1);
    const [blob] = mocked.downloadBlob.mock.calls[0]!;
    expect(blob.type).toBe('application/json');
  });

  it('disables export when nothing matches the current filters', () => {
    renderPanel([issue()]);
    fireEvent.change(screen.getByRole('textbox', { name: 'Search issues' }), {
      target: { value: 'nonexistent' },
    });
    expect(screen.getByRole('button', { name: 'Export filtered issues as JSON' })).toBeDisabled();
  });

  it('reports the filtered count against the total', () => {
    renderPanel([
      issue({ severity: 'error', code: 'e' }),
      issue({ severity: 'warning', code: 'w' }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'error' }));
    expect(screen.getByText('Showing 1 of 2 issues')).toBeInTheDocument();
  });
});
