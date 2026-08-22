import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { TradeTape } from './trade-tape';

afterEach(() => {
  cleanup();
});

function trade(price: string, eventTime: string, side = 'buy'): LiveTradeData {
  return { price, size: '1.5', side, event_time: eventTime };
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
});
