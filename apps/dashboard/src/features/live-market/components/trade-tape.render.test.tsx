import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { TradeTape } from './trade-tape';

/**
 * A render-cost regression guard for the trade tape — the "profile
 * rendering, eliminate unnecessary re-renders" half of this dashboard's
 * performance pass, expressed as an assertion rather than a one-off
 * measurement in a browser profiler that nothing would keep honest.
 *
 * The technique: every row's render calls `formatDecimal` a fixed number of
 * times (once per numeric cell). Spying on that shared formatter therefore
 * gives an exact, implementation-honest count of *how many rows actually
 * re-rendered* — something neither the DOM nor Testing Library exposes
 * directly, since React reuses DOM nodes whether or not a component's body
 * re-ran.
 *
 * Without `React.memo` on the row, adding one trade to a 100-row tape
 * re-renders all 101 rows. With it, only the new row renders.
 */
vi.mock('@/features/history/lib/format', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/history/lib/format')>();
  return { ...actual, formatDecimal: vi.fn(actual.formatDecimal) };
});

const { formatDecimal } = await import('@/features/history/lib/format');
const formatDecimalSpy = vi.mocked(formatDecimal);

/** Numeric cells per row: price and quantity (the tape's default four columns). */
const FORMAT_CALLS_PER_ROW = 2;

function trade(index: number): LiveTradeData {
  return {
    price: String(100 + index),
    size: '1.5',
    side: index % 2 === 0 ? 'buy' : 'sell',
    event_time: new Date(1_700_000_000_000 + index * 1_000).toISOString(),
  };
}

beforeEach(() => {
  formatDecimalSpy.mockClear();
});

afterEach(() => {
  cleanup();
});

describe('TradeTape render cost', () => {
  it('re-renders only the newly-arrived row when a trade is prepended, not the whole tape', () => {
    const existing = Array.from({ length: 100 }, (_, index) => trade(index));
    const { rerender } = render(
      <TradeTape trades={existing} isConnecting={false} maxTrades={200} />,
    );
    expect(formatDecimalSpy).toHaveBeenCalledTimes(existing.length * FORMAT_CALLS_PER_ROW);

    formatDecimalSpy.mockClear();
    const incoming = trade(1000);
    rerender(<TradeTape trades={[incoming, ...existing]} isConnecting={false} maxTrades={200} />);

    // Exactly one row's worth of formatting — the other 100 rows were
    // skipped by `React.memo`, because their `trade` object references and
    // every other prop are unchanged.
    expect(formatDecimalSpy).toHaveBeenCalledTimes(FORMAT_CALLS_PER_ROW);
  });

  it('re-renders no rows at all when the parent re-renders with identical props', () => {
    const trades = Array.from({ length: 50 }, (_, index) => trade(index));
    const { rerender } = render(<TradeTape trades={trades} isConnecting={false} maxTrades={200} />);

    formatDecimalSpy.mockClear();
    rerender(<TradeTape trades={trades} isConnecting={false} maxTrades={200} />);

    expect(formatDecimalSpy).not.toHaveBeenCalled();
  });

  it('re-renders only the rows whose highlight actually changed when the threshold moves', () => {
    // Values are 100×1.5 … 149×1.5, i.e. 150 … 223.5.
    const trades = Array.from({ length: 50 }, (_, index) => trade(index));
    const { rerender } = render(
      <TradeTape
        trades={trades}
        isConnecting={false}
        maxTrades={200}
        largeTradeThreshold={1_000_000}
      />,
    );

    formatDecimalSpy.mockClear();
    // Lowering the threshold to 223 newly flags only the single largest row.
    rerender(
      <TradeTape trades={trades} isConnecting={false} maxTrades={200} largeTradeThreshold={223} />,
    );

    expect(formatDecimalSpy).toHaveBeenCalledTimes(FORMAT_CALLS_PER_ROW);
  });

  it('renders only a window of rows up front when virtualized, not the entire list', () => {
    const trades = Array.from({ length: 400 }, (_, index) => trade(index));
    render(<TradeTape trades={trades} isConnecting={false} maxTrades={400} virtualize />);

    const renderedRows = formatDecimalSpy.mock.calls.length / FORMAT_CALLS_PER_ROW;
    expect(renderedRows).toBeGreaterThan(0);
    // A small fraction of 400 — the exact window size is an implementation
    // detail, but it must not scale with the list.
    expect(renderedRows).toBeLessThan(40);
  });
});
