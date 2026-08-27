import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { MLDatasetBuildListResponse, MLDatasetBuildSummary } from '@/types/api/ml-datasets';
import { DatasetHistoryTable } from './dataset-history-table';

afterEach(() => cleanup());

function build(overrides: Partial<MLDatasetBuildSummary> = {}): MLDatasetBuildSummary {
  return {
    id: 'build-1',
    ml_dataset_id: 'ml-1',
    symbol: 'ETHUSD',
    timeframe: '1h',
    row_count: 120,
    column_count: 6,
    feature_count: 4,
    target_count: 1,
    quality_passed: true,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function listResponse(builds: MLDatasetBuildSummary[]): MLDatasetBuildListResponse {
  return { builds, total: builds.length, limit: 10, offset: 0 };
}

describe('DatasetHistoryTable', () => {
  it('renders one row per past build with its quality verdict', () => {
    render(
      <ThemeProvider theme={theme}>
        <DatasetHistoryTable
          data={listResponse([build(), build({ id: 'build-2', quality_passed: false })])}
          isLoading={false}
          page={1}
          limit={10}
          sort="created_at"
          dir="desc"
          onPageChange={vi.fn()}
          onSortChange={vi.fn()}
          onSelect={vi.fn()}
          onDelete={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(screen.getAllByText('ETHUSD')).toHaveLength(2);
    expect(screen.getByText('Passed')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('shows an empty state when there are no builds', () => {
    render(
      <ThemeProvider theme={theme}>
        <DatasetHistoryTable
          data={listResponse([])}
          isLoading={false}
          page={1}
          limit={10}
          sort="created_at"
          dir="desc"
          onPageChange={vi.fn()}
          onSortChange={vi.fn()}
          onSelect={vi.fn()}
          onDelete={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(
      screen.getByText('No datasets built yet — use the builder above, and it will appear here.'),
    ).toBeInTheDocument();
  });

  it('calls onSelect when a row is clicked', () => {
    const onSelect = vi.fn();
    const entry = build();
    render(
      <ThemeProvider theme={theme}>
        <DatasetHistoryTable
          data={listResponse([entry])}
          isLoading={false}
          page={1}
          limit={10}
          sort="created_at"
          dir="desc"
          onPageChange={vi.fn()}
          onSortChange={vi.fn()}
          onSelect={onSelect}
          onDelete={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByText('ETHUSD'));
    expect(onSelect).toHaveBeenCalledWith(entry);
  });

  it('calls onDelete without triggering onSelect when the delete button is clicked', () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    const entry = build();
    render(
      <ThemeProvider theme={theme}>
        <DatasetHistoryTable
          data={listResponse([entry])}
          isLoading={false}
          page={1}
          limit={10}
          sort="created_at"
          dir="desc"
          onPageChange={vi.fn()}
          onSortChange={vi.fn()}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByLabelText('Delete ML dataset build ETHUSD 1h'));
    expect(onDelete).toHaveBeenCalledWith(entry);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('toggles sort direction when the same column header is clicked twice', () => {
    const onSortChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <DatasetHistoryTable
          data={listResponse([build()])}
          isLoading={false}
          page={1}
          limit={10}
          sort="created_at"
          dir="desc"
          onPageChange={vi.fn()}
          onSortChange={onSortChange}
          onSelect={vi.fn()}
          onDelete={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByText('Built'));
    expect(onSortChange).toHaveBeenCalledWith('created_at', 'asc');
  });

  it('sorts ascending by default when a different column is clicked', () => {
    const onSortChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <DatasetHistoryTable
          data={listResponse([build()])}
          isLoading={false}
          page={1}
          limit={10}
          sort="created_at"
          dir="desc"
          onPageChange={vi.fn()}
          onSortChange={onSortChange}
          onSelect={vi.fn()}
          onDelete={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByText('Symbol'));
    expect(onSortChange).toHaveBeenCalledWith('symbol', 'asc');
  });
});
