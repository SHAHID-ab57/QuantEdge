import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { ColumnStatsPopover } from './column-stats-popover';

afterEach(() => cleanup());

function renderPopover(values: (number | null)[] = [1, 2, 3, null], isPreviewSubset = false) {
  return render(
    <ThemeProvider theme={theme}>
      <ColumnStatsPopover columnName="close" values={values} isPreviewSubset={isPreviewSubset} />
    </ThemeProvider>,
  );
}

describe('ColumnStatsPopover', () => {
  it('renders a small icon button and no stats until clicked', () => {
    renderPopover();
    expect(screen.getByRole('button', { name: 'Show statistics for close' })).toBeInTheDocument();
    expect(screen.queryByText('Min')).not.toBeInTheDocument();
  });

  it('shows min/max/mean/std/null count when opened', () => {
    renderPopover([1, 2, 3, null]);
    fireEvent.click(screen.getByRole('button', { name: 'Show statistics for close' }));
    expect(screen.getByText('Min')).toBeInTheDocument();
    expect(screen.getByText('Max')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Mean')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Null count')).toBeInTheDocument();
    expect(screen.getAllByText('1')).toHaveLength(2); // Min value and Null count both happen to be 1
  });

  it('notes when the statistics are scoped to a preview subset', () => {
    renderPopover([1, 2, 3], true);
    fireEvent.click(screen.getByRole('button', { name: 'Show statistics for close' }));
    expect(screen.getByText(/rendered preview rows only/)).toBeInTheDocument();
  });

  it('omits the preview caveat when computed over the full dataset', () => {
    renderPopover([1, 2, 3], false);
    fireEvent.click(screen.getByRole('button', { name: 'Show statistics for close' }));
    expect(screen.queryByText(/rendered preview rows only/)).not.toBeInTheDocument();
  });

  it('does not propagate the click to an ancestor sort/expand handler', () => {
    let bubbled = false;
    render(
      <ThemeProvider theme={theme}>
        <div onClick={() => (bubbled = true)}>
          <ColumnStatsPopover columnName="close" values={[1]} isPreviewSubset={false} />
        </div>
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Show statistics for close' }));
    expect(bubbled).toBe(false);
  });
});
