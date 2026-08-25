import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { ValidationReport } from '@/types/api/dataset-validation';
import { ValidationStatistics } from './validation-statistics';

function report(overrides: Partial<ValidationReport> = {}): ValidationReport {
  return {
    dataset_id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    timeframe: '1h',
    engine_version: '1.0.0',
    validated_at: '2026-01-01T00:00:00Z',
    passed: true,
    rules_run: ['required_columns', 'data_types'],
    summary: { total_checks: 0, errors: 0, warnings: 0, info: 0 },
    categories: {},
    issues: [],
    rows: 480,
    columns: 5,
    duration_ms: 12.34,
    ...overrides,
  };
}

function renderStatistics(props: Partial<React.ComponentProps<typeof ValidationStatistics>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <ValidationStatistics report={report()} {...props} />
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe('ValidationStatistics', () => {
  it('shows the dataset id, market, and timeframe', () => {
    renderStatistics();
    expect(screen.getByText('11111111-1111-4111-8111-111111111111')).toBeInTheDocument();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('1h')).toBeInTheDocument();
  });

  it('shows rows and columns', () => {
    renderStatistics();
    expect(screen.getByText('480')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('shows the duration formatted to one decimal place', () => {
    renderStatistics();
    expect(screen.getByText('12.3 ms')).toBeInTheDocument();
  });

  it('lists every rule that ran', () => {
    renderStatistics();
    expect(screen.getByText('Rules run (2)')).toBeInTheDocument();
    expect(screen.getByText('required_columns')).toBeInTheDocument();
    expect(screen.getByText('data_types')).toBeInTheDocument();
  });
});
