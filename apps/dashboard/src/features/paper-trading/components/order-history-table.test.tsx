import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { PaperOrderListResponse } from '@/types/api/paper-trading';
import { OrderHistoryTable } from './order-history-table';

const DATA: PaperOrderListResponse = {
  orders: [
    {
      id: 'order-1',
      account_id: 'account-1',
      symbol: 'ETHUSD',
      side: 'buy',
      quantity: '10',
      raw_price: '1000',
      fill_price: '1000.5',
      fill_time: '2026-01-01T00:00:00Z',
      price_source: 'ticker',
      price_observed_at: '2026-01-01T00:00:00Z',
      is_stale_price: false,
      slippage_applied: '0.5',
      fee_applied: '10.005',
      notional: '10005',
      realized_pnl: null,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

afterEach(() => cleanup());

function renderTable(overrides: Partial<Parameters<typeof OrderHistoryTable>[0]> = {}) {
  render(
    <ThemeProvider theme={theme}>
      <OrderHistoryTable
        data={DATA}
        isLoading={false}
        page={1}
        limit={20}
        onPageChange={() => {}}
        {...overrides}
      />
    </ThemeProvider>,
  );
}

describe('OrderHistoryTable', () => {
  it('renders fill price, source, and slippage/fee for each order', () => {
    renderTable();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('$1000.5000')).toBeInTheDocument();
    expect(screen.getByText('ticker')).toBeInTheDocument();
    expect(screen.getByText('$0.5000 / $10.0050')).toBeInTheDocument();
  });

  it('shows a dash for a buy order (no realized PnL)', () => {
    renderTable();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('shows a realized PnL value for a sell order', () => {
    renderTable({
      data: {
        ...DATA,
        orders: [
          {
            ...DATA.orders[0]!,
            id: 'order-2',
            side: 'sell',
            realized_pnl: '978.5055',
          },
        ],
      },
    });
    expect(screen.getByText('+$978.51')).toBeInTheDocument();
  });

  it('marks a stale-priced fill with a warning chip', () => {
    renderTable({
      data: {
        ...DATA,
        orders: [{ ...DATA.orders[0]!, price_source: 'candle_close', is_stale_price: true }],
      },
    });
    expect(screen.getByText('candle_close')).toBeInTheDocument();
  });

  it('reports an empty history', () => {
    renderTable({ data: { orders: [], total: 0, limit: 20, offset: 0 } });
    expect(
      screen.getByText('No orders yet — place one above, and it will appear here.'),
    ).toBeInTheDocument();
  });
});
