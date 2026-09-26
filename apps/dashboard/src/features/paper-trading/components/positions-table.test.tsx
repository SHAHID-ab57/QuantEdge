import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { PaperPositionListResponse } from '@/types/api/paper-trading';
import { PositionsTable } from './positions-table';

const DATA: PaperPositionListResponse = {
  positions: [
    {
      symbol: 'ETHUSD',
      side: 'long',
      quantity: '10',
      average_entry_price: '1000.5',
      leverage: '1',
      margin: '10005',
      liquidation_price: null,
      liquidation_distance_pct: null,
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
      <PositionsTable
        data={DATA}
        isLoading={false}
        onEditThresholds={vi.fn()}
        onClosePosition={vi.fn()}
        {...overrides}
      />
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
      screen.getByText('No open positions — place an order above to open one.'),
    ).toBeInTheDocument();
  });

  it('shows a dash for unset stop-loss/take-profit and the real values once set', () => {
    const { rerender } = render(
      <ThemeProvider theme={theme}>
        <PositionsTable
          data={DATA}
          isLoading={false}
          onEditThresholds={vi.fn()}
          onClosePosition={vi.fn()}
        />
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
          onClosePosition={vi.fn()}
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

describe('PositionsTable — shorts, leverage and liquidation', () => {
  const SHORT: PaperPositionListResponse['positions'][number] = {
    ...DATA.positions[0]!,
    side: 'short',
    quantity: '5',
    leverage: '5',
    margin: '1999',
    average_entry_price: '1999.5',
    liquidation_price: '2392.82',
    liquidation_distance_pct: '19.6',
    current_price: '2000',
    unrealized_pnl: '-5',
  };

  it('shows a short as a Short with its leverage, margin and liquidation price', () => {
    renderTable({ data: { positions: [SHORT] } });
    expect(screen.getByText('Short')).toBeInTheDocument();
    expect(screen.getByText('5x')).toBeInTheDocument();
    expect(screen.getByText('$1999.00', { selector: 'td' })).toBeInTheDocument();
    expect(screen.getByText('$2392.82 (19.6% away)')).toBeInTheDocument();
  });

  it('shows a long as a Long, and a dash for a 1x long which cannot be liquidated', () => {
    renderTable();
    expect(screen.getByText('Long')).toBeInTheDocument();
    expect(screen.getByText('1x')).toBeInTheDocument();
    const cells = screen.getAllByRole('cell');
    expect(cells.some((cell) => cell.textContent === '—')).toBe(true);
    expect(screen.queryByText(/% away/)).not.toBeInTheDocument();
  });

  it('marks a position close to its liquidation price', () => {
    renderTable({
      data: {
        positions: [{ ...SHORT, liquidation_distance_pct: '4.2', liquidation_price: '2090' }],
      },
    });
    const near = screen.getByText('$2090.00 (4.2% away)');
    expect(getComputedStyle(near).fontWeight).toBe('700');
  });

  it('closes a position via the Close action, passing the whole position', () => {
    const onClosePosition = vi.fn();
    renderTable({ data: { positions: [SHORT] }, onClosePosition });
    fireEvent.click(screen.getByRole('button', { name: 'Close ETHUSD short position' }));
    expect(onClosePosition).toHaveBeenCalledWith(SHORT);
  });
});
