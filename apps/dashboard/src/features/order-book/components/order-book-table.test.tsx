import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { DepthRow } from '../lib/order-book-depth';
import { OrderBookTable, orderBookRowPropsAreEqual } from './order-book-table';

afterEach(() => {
  cleanup();
});

function row(price: number, size: number, total: number, depthRatio: number): DepthRow {
  return { price, size, total, depthRatio };
}

function renderTable(side: 'bids' | 'asks', rows: DepthRow[]) {
  return render(
    <ThemeProvider theme={theme}>
      <OrderBookTable side={side} rows={rows} />
    </ThemeProvider>,
  );
}

describe('OrderBookTable', () => {
  it('renders bid columns in Total, Size, Price order', () => {
    renderTable('bids', [row(100, 1, 1, 1)]);
    const headers = screen.getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers).toEqual(['Total', 'Size', 'Price']);
  });

  it('renders ask columns in Price, Size, Total order', () => {
    renderTable('asks', [row(101, 1, 1, 1)]);
    const headers = screen.getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers).toEqual(['Price', 'Size', 'Total']);
  });

  it('renders one row per level with price, size, and cumulative total', () => {
    renderTable('bids', [row(100, 2, 2, 1), row(99, 3, 5, 0.4)]);
    const rows = screen.getAllByRole('row').slice(1); // drop the header row
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText('100.00')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('2.00')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('5')).toBeInTheDocument(); // cumulative total
  });

  it('renders an empty table without crashing when there are no levels', () => {
    renderTable('bids', []);
    expect(screen.getAllByRole('row')).toHaveLength(1); // header only
  });

  it('renders a 100-level book without dropping any row', () => {
    const rows = Array.from({ length: 100 }, (_, i) => row(1000 - i, 1, i + 1, (i + 1) / 100));
    renderTable('bids', rows);
    expect(screen.getAllByRole('row')).toHaveLength(101); // header + 100 levels
  });
});

describe('orderBookRowPropsAreEqual (React.memo comparator)', () => {
  const base = {
    row: row(100, 1, 1, 1),
    isBids: true,
    barColor: 'rgba(0,0,0,0.1)',
    priceColor: 'success.main',
  };

  it('treats two objects with identical values as equal, even with different references', () => {
    const same = { ...base, row: row(100, 1, 1, 1) }; // a new row object, same values
    expect(orderBookRowPropsAreEqual(base, same)).toBe(true);
  });

  it('detects a changed price', () => {
    expect(orderBookRowPropsAreEqual(base, { ...base, row: row(101, 1, 1, 1) })).toBe(false);
  });

  it('detects a changed size', () => {
    expect(orderBookRowPropsAreEqual(base, { ...base, row: row(100, 2, 1, 1) })).toBe(false);
  });

  it('detects a changed cumulative total', () => {
    expect(orderBookRowPropsAreEqual(base, { ...base, row: row(100, 1, 5, 1) })).toBe(false);
  });

  it('detects a changed depth ratio (another row in the book moved)', () => {
    expect(orderBookRowPropsAreEqual(base, { ...base, row: row(100, 1, 1, 0.5) })).toBe(false);
  });

  it('detects a side flip', () => {
    expect(orderBookRowPropsAreEqual(base, { ...base, isBids: false })).toBe(false);
  });

  it('detects a theme-driven color change', () => {
    expect(orderBookRowPropsAreEqual(base, { ...base, barColor: 'rgba(1,1,1,0.1)' })).toBe(false);
  });
});
