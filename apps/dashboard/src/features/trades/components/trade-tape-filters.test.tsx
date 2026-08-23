import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradeTapeFilters, type TradeTapeFiltersProps } from './trade-tape-filters';

afterEach(() => {
  cleanup();
});

function renderFilters(overrides: Partial<TradeTapeFiltersProps> = {}) {
  return render(
    <TradeTapeFilters
      side="all"
      onSideChange={vi.fn()}
      minSize={0}
      onMinSizeChange={vi.fn()}
      visibleCount={10}
      totalCount={10}
      {...overrides}
    />,
  );
}

describe('TradeTapeFilters', () => {
  it('calls onSideChange when a side toggle is clicked', () => {
    const onSideChange = vi.fn();
    renderFilters({ onSideChange });
    fireEvent.click(screen.getByRole('button', { name: 'Show Buy trades' }));
    expect(onSideChange).toHaveBeenCalledWith('buy');
  });

  it('does not call onSideChange when clicking the already-selected option', () => {
    const onSideChange = vi.fn();
    renderFilters({ onSideChange });
    fireEvent.click(screen.getByRole('button', { name: 'Show All trades' }));
    expect(onSideChange).not.toHaveBeenCalled();
  });

  it('reports a typed minimum size as a number', () => {
    const onMinSizeChange = vi.fn();
    renderFilters({ onMinSizeChange });
    fireEvent.change(screen.getByLabelText('Minimum trade size'), { target: { value: '5' } });
    expect(onMinSizeChange).toHaveBeenLastCalledWith(5);
  });

  it('falls back to 0 for an invalid or empty typed value', () => {
    const onMinSizeChange = vi.fn();
    renderFilters({ minSize: 5, onMinSizeChange });
    fireEvent.change(screen.getByLabelText('Minimum trade size'), { target: { value: '' } });
    expect(onMinSizeChange).toHaveBeenLastCalledWith(0);
  });

  it('says all rows are showing when nothing is filtered out', () => {
    renderFilters({ visibleCount: 10, totalCount: 10 });
    expect(screen.getByLabelText('Trade tape filter result')).toHaveTextContent(
      'Showing all 10 rows',
    );
  });

  it('makes it explicit when rows are being hidden, so a filtered tape is not mistaken for a quiet market', () => {
    renderFilters({ visibleCount: 3, totalCount: 10 });
    expect(screen.getByLabelText('Trade tape filter result')).toHaveTextContent(
      'Showing 3 of 10 rows',
    );
  });

  it('renders an action slot when given one', () => {
    renderFilters({ action: <button type="button">Export CSV</button> });
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
  });
});
