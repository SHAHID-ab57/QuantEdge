import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { ValidationReport } from '@/types/api/dataset-validation';
import { ValidationSummaryCards } from './validation-summary-cards';

function report(overrides: Partial<ValidationReport> = {}): ValidationReport {
  return {
    dataset_id: 'abc',
    symbol: 'ETHUSD',
    timeframe: '1h',
    engine_version: '1.0.0',
    validated_at: '2026-01-01T00:00:00Z',
    passed: true,
    rules_run: ['required_columns'],
    summary: { total_checks: 0, errors: 0, warnings: 0, info: 0 },
    categories: {
      structural: { errors: 0, warnings: 0, info: 0 },
      data_quality: { errors: 0, warnings: 0, info: 0 },
      time_series: { errors: 0, warnings: 0, info: 0 },
      feature: { errors: 0, warnings: 0, info: 0 },
    },
    issues: [],
    rows: 480,
    columns: 7,
    duration_ms: 1.2,
    ...overrides,
  };
}

function renderCards(props: Partial<React.ComponentProps<typeof ValidationSummaryCards>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <ValidationSummaryCards report={report()} featureCount={3} {...props} />
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe('ValidationSummaryCards — verdict', () => {
  it('shows "Passed" when the gate passed', () => {
    renderCards();
    expect(screen.getByText('Passed')).toBeInTheDocument();
  });

  it('shows "Failed" when the gate did not pass', () => {
    renderCards({
      report: report({
        passed: false,
        summary: { total_checks: 1, errors: 1, warnings: 0, info: 0 },
      }),
    });
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('shows the error, warning, and info counts', () => {
    renderCards({
      report: report({ summary: { total_checks: 17, errors: 2, warnings: 6, info: 9 } }),
    });
    // Chosen to not collide with the fixture's rows(480)/columns(7)/featureCount(3).
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
  });
});

describe('ValidationSummaryCards — category breakdown', () => {
  it('marks a clean category as "Clean"', () => {
    renderCards();
    expect(screen.getAllByText('Clean').length).toBe(4);
  });

  it('shows a categorys error/warning/info breakdown when it has findings', () => {
    renderCards({
      report: report({
        categories: {
          structural: { errors: 1, warnings: 2, info: 0 },
          data_quality: { errors: 0, warnings: 0, info: 0 },
          time_series: { errors: 0, warnings: 0, info: 0 },
          feature: { errors: 0, warnings: 0, info: 0 },
        },
      }),
    });
    expect(screen.getByText('1E · 2W · 0I')).toBeInTheDocument();
  });

  it('labels every category', () => {
    renderCards();
    expect(screen.getByText('Structural')).toBeInTheDocument();
    expect(screen.getByText('Data Quality')).toBeInTheDocument();
    expect(screen.getByText('Time-Series')).toBeInTheDocument();
    expect(screen.getByText('Feature')).toBeInTheDocument();
  });
});

describe('ValidationSummaryCards — dataset shape', () => {
  it('shows dataset size as rows times columns', () => {
    renderCards();
    expect(screen.getByText('3,360')).toBeInTheDocument(); // 480 * 7
  });

  it('shows rows and columns', () => {
    renderCards();
    expect(screen.getByText('480')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });

  it('shows how many features were requested', () => {
    renderCards({ featureCount: 5 });
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('shows how many rules ran', () => {
    renderCards({ report: report({ rules_run: ['a', 'b', 'c'] }) });
    // Rules Executed shows the count, distinct from featureCount=3 by querying via the label.
    expect(screen.getByText('Rules Executed').closest('div')?.parentElement).toHaveTextContent('3');
  });

  it('shows validation time', () => {
    renderCards({ report: report({ duration_ms: 12.34 }) });
    expect(screen.getByText('12.3 ms')).toBeInTheDocument();
  });
});

describe('ValidationSummaryCards — quality score', () => {
  it('is 100 for a perfectly clean report', () => {
    renderCards();
    expect(screen.getByText('Quality Score').parentElement?.parentElement).toHaveTextContent('100');
  });

  it('is lower for a report with errors and warnings', () => {
    renderCards({
      report: report({ summary: { total_checks: 3, errors: 1, warnings: 1, info: 0 } }),
    });
    // 100 - 15 (one error) - 5 (one warning) = 80.
    expect(screen.getByText('Quality Score').parentElement?.parentElement).toHaveTextContent('80');
  });
});
