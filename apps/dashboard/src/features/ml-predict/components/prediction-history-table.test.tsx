import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { PredictionListResponse } from '@/types/api/prediction';
import { PredictionHistoryTable } from './prediction-history-table';

const DATA: PredictionListResponse = {
  predictions: [
    {
      id: 'pred-1',
      training_job_id: 'job-1',
      experiment_id: 'exp-1',
      symbol: 'ETHUSD',
      timeframe: '1h',
      model_type: 'logistic_regression',
      model_kind: 'classification',
      target_column: 'next_direction_1',
      horizon: 1,
      as_of: '2026-01-05T12:00:00Z',
      predicted_value: 'up',
      confidence: 0.8,
      created_at: '2026-01-05T12:05:00Z',
    },
  ],
  total: 1,
  limit: 10,
  offset: 0,
};

afterEach(() => cleanup());

function renderTable(overrides: Partial<Parameters<typeof PredictionHistoryTable>[0]> = {}) {
  const onReopen = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <PredictionHistoryTable
        data={DATA}
        isLoading={false}
        page={1}
        limit={10}
        onPageChange={vi.fn()}
        onReopen={onReopen}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { onReopen };
}

describe('PredictionHistoryTable', () => {
  it('renders one row per past prediction', () => {
    renderTable();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('next_direction_1')).toBeInTheDocument();
    expect(screen.getByText('up')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
  });

  it('shows a dash instead of a confidence chip when confidence is null', () => {
    renderTable({
      data: {
        ...DATA,
        predictions: [{ ...DATA.predictions[0]!, confidence: null }],
      },
    });
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('calls onReopen with the clicked row', () => {
    const { onReopen } = renderTable();
    fireEvent.click(screen.getByRole('button', { name: 'Reopen prediction pred-1' }));
    expect(onReopen).toHaveBeenCalledWith(DATA.predictions[0]);
  });

  it('reports an empty result', () => {
    renderTable({ data: { ...DATA, predictions: [], total: 0 } });
    expect(
      screen.getByText('No predictions yet — run one above, and it will appear here.'),
    ).toBeInTheDocument();
  });

  it('shows loading rows while fetching the first page', () => {
    renderTable({ data: undefined, isLoading: true });
    expect(document.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
  });
});
