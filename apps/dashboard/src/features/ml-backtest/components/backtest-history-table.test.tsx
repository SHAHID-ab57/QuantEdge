import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { BacktestListResponse } from '@/types/api/backtest';
import { BacktestHistoryTable } from './backtest-history-table';

const DATA: BacktestListResponse = {
  runs: [
    {
      id: 'run-1',
      training_job_id: 'job-1',
      symbol: 'ETHUSD',
      timeframe: '1h',
      step: '1h',
      status: 'completed',
      truncated: false,
      total_steps: 5,
      completed_steps: 5,
      graded_count: 5,
      created_at: '2026-01-01T00:00:00Z',
      completed_at: '2026-01-01T00:05:00Z',
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

afterEach(() => cleanup());

function renderTable(overrides: Partial<Parameters<typeof BacktestHistoryTable>[0]> = {}) {
  const onReopen = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <BacktestHistoryTable
        data={DATA}
        isLoading={false}
        page={1}
        limit={20}
        onPageChange={vi.fn()}
        onReopen={onReopen}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { onReopen };
}

describe('BacktestHistoryTable', () => {
  it('renders one row per past run', () => {
    renderTable();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('5/5')).toBeInTheDocument();
  });

  it('marks a truncated run distinctly', () => {
    renderTable({
      data: { ...DATA, runs: [{ ...DATA.runs[0]!, truncated: true }] },
    });
    expect(screen.getByText('5/5 *')).toBeInTheDocument();
  });

  it('reports an empty history', () => {
    renderTable({ data: { runs: [], total: 0, limit: 20, offset: 0 } });
    expect(
      screen.getByText('No past backtests yet — run one above, and it will appear here.'),
    ).toBeInTheDocument();
  });

  it('calls onReopen when the reopen action is clicked', () => {
    const { onReopen } = renderTable();
    screen.getByLabelText('Reopen backtest run-1').click();
    expect(onReopen).toHaveBeenCalledWith(DATA.runs[0]);
  });
});
