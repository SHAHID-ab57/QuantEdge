import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { BenchmarkRunListResponse } from '@/types/api/evaluation';
import { BenchmarkHistoryTable } from './benchmark-history-table';

const DATA: BenchmarkRunListResponse = {
  runs: [
    {
      id: 'run-1',
      dataset_version: 'ds-1',
      target_column: 'next_direction',
      candidate_count: 2,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

afterEach(() => cleanup());

function renderTable(overrides: Partial<Parameters<typeof BenchmarkHistoryTable>[0]> = {}) {
  const onReopen = vi.fn();
  const onDelete = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <BenchmarkHistoryTable
        data={DATA}
        isLoading={false}
        page={1}
        limit={20}
        onPageChange={vi.fn()}
        onReopen={onReopen}
        onDelete={onDelete}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { onReopen, onDelete };
}

describe('BenchmarkHistoryTable', () => {
  it('renders one row per past run', () => {
    renderTable();
    expect(screen.getByText('ds-1')).toBeInTheDocument();
    expect(screen.getByText('next_direction')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('reports an empty history', () => {
    renderTable({ data: { runs: [], total: 0, limit: 20, offset: 0 } });
    expect(
      screen.getByText('No past comparisons yet — run one above, and it will appear here.'),
    ).toBeInTheDocument();
  });

  it('calls onReopen when the reopen action is clicked', () => {
    const { onReopen } = renderTable();
    screen.getByLabelText('Reopen benchmark run run-1').click();
    expect(onReopen).toHaveBeenCalledWith(DATA.runs[0]);
  });

  it('calls onDelete when the delete action is clicked', () => {
    const { onDelete } = renderTable();
    screen.getByLabelText('Delete benchmark run run-1').click();
    expect(onDelete).toHaveBeenCalledWith(DATA.runs[0]);
  });
});
