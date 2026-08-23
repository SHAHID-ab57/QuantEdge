import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { TradeTape } from './trade-tape';

afterEach(() => {
  cleanup();
});

function trade(price: string, eventTime: string, side = 'buy', size = '1.5'): LiveTradeData {
  return { price, size, side, event_time: eventTime };
}

describe('TradeTape', () => {
  it('shows a connecting skeleton when there are no trades yet and still connecting', () => {
    render(<TradeTape trades={[]} isConnecting maxTrades={100} />);
    expect(screen.getByRole('status', { name: 'Connecting to trade stream' })).toBeInTheDocument();
  });

  it('explains the empty tape rather than just saying "no trades"', () => {
    render(<TradeTape trades={[]} isConnecting={false} maxTrades={100} />);
    expect(screen.getByRole('status')).toHaveTextContent('no trades have printed yet');
  });

  it('renders trades newest-first with time, price, quantity, and side columns', () => {
    const trades = [trade('101', '2026-01-01T00:00:01Z'), trade('100', '2026-01-01T00:00:00Z')];
    render(<TradeTape trades={trades} isConnecting={false} maxTrades={100} />);

    for (const name of ['Time', 'Price', 'Quantity', 'Side']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument();
    }

    const rows = screen.getAllByRole('row').slice(1); // drop the header row
    expect(rows[0]).toHaveTextContent('101.00');
    expect(rows[1]).toHaveTextContent('100.00');
  });

  it('labels buy and sell trades from the exchange-reported side', () => {
    const trades = [
      trade('101', '2026-01-01T00:00:01Z', 'buy'),
      trade('100', '2026-01-01T00:00:00Z', 'sell'),
    ];
    render(<TradeTape trades={trades} isConnecting={false} maxTrades={100} />);
    const rows = screen.getAllByRole('row').slice(1);
    expect(within(rows[0]!).getByText('Buy')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('Sell')).toBeInTheDocument();
  });

  it('degrades an unrecognized side to Unknown instead of guessing', () => {
    render(
      <TradeTape
        trades={[trade('101', '2026-01-01T00:00:01Z', 'something-else')]}
        isConnecting={false}
        maxTrades={100}
      />,
    );
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('states the retention cap so the truncated tape is not a mystery', () => {
    render(<TradeTape trades={[]} isConnecting={false} maxTrades={50} />);
    expect(screen.getByText('newest first · last 50')).toBeInTheDocument();
  });

  it('renders whatever list it is given (capping itself is the hook’s job)', () => {
    const trades = Array.from({ length: 5 }, (_, index) =>
      trade(String(100 + index), `2026-01-01T00:00:0${index}Z`),
    );
    render(<TradeTape trades={trades} isConnecting={false} maxTrades={100} />);
    expect(screen.getAllByRole('row')).toHaveLength(6); // 1 header + 5 trades
  });

  it('omits the Trade Value column by default, unchanged from before', () => {
    render(
      <TradeTape
        trades={[trade('100', '2026-01-01T00:00:00Z')]}
        isConnecting={false}
        maxTrades={100}
      />,
    );
    expect(screen.queryByRole('columnheader', { name: 'Trade Value' })).not.toBeInTheDocument();
  });

  it('adds a Trade Value column (price × quantity) when requested', () => {
    render(
      <TradeTape
        trades={[trade('100', '2026-01-01T00:00:00Z', 'buy', '2')]}
        isConnecting={false}
        maxTrades={100}
        showTradeValue
      />,
    );
    expect(screen.getByRole('columnheader', { name: 'Trade Value' })).toBeInTheDocument();
    const row = screen.getAllByRole('row')[1]!;
    expect(within(row).getByText('200.00')).toBeInTheDocument(); // 100 * 2
  });

  it('does not highlight anything when no largeTradeThreshold is given, unchanged from before', () => {
    render(
      <TradeTape
        trades={[trade('1000000', '2026-01-01T00:00:00Z', 'buy', '1000')]}
        isConnecting={false}
        maxTrades={100}
      />,
    );
    expect(screen.queryByText('Large')).not.toBeInTheDocument();
  });

  it('marks a trade at or above largeTradeThreshold as Large, and leaves smaller ones alone', () => {
    const trades = [
      trade('1000', '2026-01-01T00:00:01Z', 'buy', '1'), // value 1000 — large
      trade('1', '2026-01-01T00:00:00Z', 'buy', '1'), // value 1 — not large
    ];
    render(
      <TradeTape trades={trades} isConnecting={false} maxTrades={100} largeTradeThreshold={100} />,
    );
    const rows = screen.getAllByRole('row').slice(1);
    expect(within(rows[0]!).getByText('Large')).toBeInTheDocument();
    expect(within(rows[1]!).queryByText('Large')).not.toBeInTheDocument();
  });

  it('renders every row when virtualization is off, however long the list', () => {
    const trades = Array.from({ length: 120 }, (_, index) =>
      trade(String(100 + index), new Date(1_700_000_000_000 + index * 1_000).toISOString()),
    );
    render(<TradeTape trades={trades} isConnecting={false} maxTrades={200} />);
    expect(screen.getAllByRole('row')).toHaveLength(121); // 1 header + 120 trades
  });

  it('renders only a window of rows when virtualized, but reports the full count to assistive tech', () => {
    const trades = Array.from({ length: 200 }, (_, index) =>
      trade(String(100 + index), new Date(1_700_000_000_000 + index * 1_000).toISOString()),
    );
    render(<TradeTape trades={trades} isConnecting={false} maxTrades={200} virtualize />);

    const rendered = screen.getAllByRole('row').length - 1; // drop the header
    expect(rendered).toBeGreaterThan(0);
    expect(rendered).toBeLessThan(trades.length);
    // The spacer rows that reserve the skipped height are aria-hidden, so
    // they are not counted above — but the real total is still announced.
    expect(screen.getByRole('table', { name: 'Recent trades' })).toHaveAttribute(
      'aria-rowcount',
      '200',
    );
  });

  it('does not virtualize a short list even when asked, since there is nothing to save', () => {
    const trades = Array.from({ length: 10 }, (_, index) =>
      trade(String(100 + index), new Date(1_700_000_000_000 + index * 1_000).toISOString()),
    );
    render(<TradeTape trades={trades} isConnecting={false} maxTrades={200} virtualize />);
    expect(screen.getAllByRole('row')).toHaveLength(11); // 1 header + all 10 trades
  });

  it('renders an action slot in the header when given one', () => {
    render(
      <TradeTape
        trades={[]}
        isConnecting={false}
        maxTrades={100}
        action={<button type="button">Export</button>}
      />,
    );
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('marks every column header as a column scope for screen readers', () => {
    render(
      <TradeTape
        trades={[trade('100', '2026-01-01T00:00:00Z')]}
        isConnecting={false}
        maxTrades={100}
      />,
    );
    for (const name of ['Time', 'Price', 'Quantity', 'Side']) {
      expect(screen.getByRole('columnheader', { name })).toHaveAttribute('scope', 'col');
    }
  });

  it('keeps a stable row identity across re-renders so only a genuinely new trade mounts fresh', () => {
    const existing = trade('100', '2026-01-01T00:00:00Z');
    const { rerender } = render(
      <TradeTape trades={[existing]} isConnecting={false} maxTrades={100} />,
    );
    const rowBefore = screen.getAllByRole('row')[1]!;

    const incoming = trade('101', '2026-01-01T00:00:01Z');
    rerender(<TradeTape trades={[incoming, existing]} isConnecting={false} maxTrades={100} />);

    const rowsAfter = screen.getAllByRole('row').slice(1);
    // The pre-existing trade's row is the very same DOM node — it never
    // remounted just because its array index shifted from 0 to 1.
    expect(rowsAfter[1]).toBe(rowBefore);
  });
});
