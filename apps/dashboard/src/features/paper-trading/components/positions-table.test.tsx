import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { PaperPositionListResponse } from '@/types/api/paper-trading';
import { PositionsTable } from './positions-table';

const DATA: PaperPositionListResponse = {
  positions: [
    {
      symbol: 'ETHUSD',
      quantity: '10',
      average_entry_price: '1000.5',
      current_price: '1100',
      price_source: 'ticker',
      unrealized_pnl: '995',
      stop_loss_price: null,
      take_profit_price: null,
    },
  ],
};

afterEach(() => cleanup());

function renderTable(overrides: Partial<Parameters<typeof PositionsTable>[0]> = {}) {
  render(
    <ThemeProvider theme={theme}>
      <PositionsTable data={DATA} isLoading={false} onEditThresholds={vi.fn()} {...overrides} />
    </ThemeProvider>,
  );
}

describe('PositionsTable', () => {
  it('renders one row per open position with a live mark-to-market PnL', () => {
    renderTable();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('$1000.50')).toBeInTheDocument();
    expect(screen.getByText('$1100.00')).toBeInTheDocument();
    expect(screen.getByText('+$995.00')).toBeInTheDocument();
  });

  it('renders a negative unrealized PnL without a leading plus sign', () => {
    renderTable({
      data: { positions: [{ ...DATA.positions[0]!, unrealized_pnl: '-50' }] },
    });
    expect(screen.getByText('-$50.00')).toBeInTheDocument();
  });

  it('reports no open positions', () => {
    renderTable({ data: { positions: [] } });
    expect(
      screen.getByText('No open positions — place a buy order above to open one.'),
    ).toBeInTheDocument();
  });

  it('shows a dash for unset stop-loss/take-profit and the real values once set', () => {
    const { rerender } = render(
      <ThemeProvider theme={theme}>
        <PositionsTable data={DATA} isLoading={false} onEditThresholds={vi.fn()} />
      </ThemeProvider>,
    );
    expect(screen.getByText('— / —')).toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <PositionsTable
          data={{
            positions: [
              { ...DATA.positions[0]!, stop_loss_price: '900', take_profit_price: '1200' },
            ],
          }}
          isLoading={false}
          onEditThresholds={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('$900.00 / $1200.00')).toBeInTheDocument();
  });

  it('calls onEditThresholds with the row symbol when the edit action is clicked', () => {
    const onEditThresholds = vi.fn();
    renderTable({ onEditThresholds });
    screen.getByRole('button', { name: 'Edit stop-loss/take-profit for ETHUSD' }).click();
    expect(onEditThresholds).toHaveBeenCalledWith('ETHUSD');
  });
});
