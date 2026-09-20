import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import type { PaperPosition } from '@/types/api/paper-trading';
import { OrderForm, type OrderFormValues } from './order-form';

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
}));

const mockedMarketApi = vi.mocked(marketApi);

const HELD_LONG: PaperPosition = {
  symbol: 'ETHUSD',
  side: 'long',
  quantity: '2',
  average_entry_price: '2000',
  leverage: '5',
  margin: '800',
  liquidation_price: '1604.81',
  liquidation_distance_pct: '19.8',
  current_price: '2000',
  price_source: 'ticker',
  unrealized_pnl: '0',
  stop_loss_price: null,
  take_profit_price: null,
};

beforeEach(() => {
  mockedMarketApi.fetchMarkets.mockResolvedValue({
    markets: [
      {
        id: 'market-1',
        symbol: 'ETHUSD',
        exchange: 'Delta Exchange',
        exchange_id: '11111111-1111-4111-8111-111111111111',
        base_asset: 'ETH',
        quote_asset: 'USD',
        market_type: 'perpetual',
        is_active: true,
        delta_product_id: null,
        delta_contract_type: null,
        tick_size: null,
        funding_method: null,
        funding_interval_seconds: null,
        listing_date: null,
      },
    ],
    total: 1,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderForm(props: Partial<Parameters<typeof OrderForm>[0]> = {}) {
  const onSubmit = vi.fn<(values: OrderFormValues) => void>();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <OrderForm
        onSubmit={onSubmit}
        submitting={false}
        hasAccount
        positions={[]}
        maxLeverage={5}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onSubmit };
}

async function pickMarket() {
  fireEvent.mouseDown(screen.getByLabelText('Market'));
  fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
}

function enterQuantity(value: string) {
  fireEvent.change(screen.getByLabelText('Quantity'), { target: { value } });
}

describe('OrderForm — shorts and leverage', () => {
  it('says a sell against nothing opens a short, and submits it with the chosen leverage', async () => {
    const { onSubmit } = renderForm();
    await pickMarket();
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    enterQuantity('2');

    expect(screen.getByText('Opens a new short position in ETHUSD.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Leverage'), { target: { value: '3' } });

    fireEvent.click(screen.getByRole('button', { name: 'Sell ETHUSD' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Sell' }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0]![0]).toMatchObject({
      symbol: 'ETHUSD',
      side: 'sell',
      quantity: '2',
      leverage: '3',
    });
  });

  it('warns that a short can be liquidated', async () => {
    renderForm();
    await pickMarket();
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    enterQuantity('1');
    expect(screen.getByText(/A short position can be/)).toBeInTheDocument();
    expect(screen.getByText(/whole margin posted is forfeited/)).toBeInTheDocument();
  });

  it('does not send a leverage field for a 1x order', async () => {
    const { onSubmit } = renderForm();
    await pickMarket();
    enterQuantity('1');
    fireEvent.click(screen.getByRole('button', { name: 'Buy ETHUSD' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Buy' }));
    expect(onSubmit.mock.calls[0]![0].leverage).toBeUndefined();
    expect(onSubmit.mock.calls[0]![0].reduceOnly).toBeUndefined();
  });

  it("rejects leverage above the account's maximum and disables submitting", async () => {
    renderForm({ maxLeverage: 3 });
    await pickMarket();
    enterQuantity('1');
    fireEvent.change(screen.getByLabelText('Leverage'), { target: { value: '5' } });
    expect(screen.getByText('Enter a leverage from 1 to 3.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Buy ETHUSD' })).toBeDisabled();
  });

  it('offers no leverage above 1x on an account whose maximum is not yet known', async () => {
    renderForm({ maxLeverage: undefined });
    await pickMarket();
    enterQuantity('1');
    fireEvent.change(screen.getByLabelText('Leverage'), { target: { value: '2' } });
    expect(screen.getByRole('button', { name: 'Buy ETHUSD' })).toBeDisabled();
  });
});

describe('OrderForm — what the order does to an open position', () => {
  it('says a sell against a long reduces it, and hides leverage and thresholds', async () => {
    renderForm({ positions: [HELD_LONG] });
    await pickMarket();
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    enterQuantity('1');

    expect(screen.getByText('Reduces your long position in ETHUSD.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Leverage')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Stop-loss price')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Take-profit price')).not.toBeInTheDocument();
  });

  it("refuses an order larger than the position it reduces (it can't flip through zero)", async () => {
    renderForm({ positions: [HELD_LONG] });
    await pickMarket();
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    enterQuantity('3');

    expect(screen.getByText(/can't flip a position through zero/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sell ETHUSD' })).toBeDisabled();
  });

  it("says a buy adds to a long and shows the position's own fixed leverage", async () => {
    renderForm({ positions: [HELD_LONG] });
    await pickMarket();
    enterQuantity('1');
    expect(screen.getByText('Adds to your long position in ETHUSD.')).toBeInTheDocument();
    expect(screen.getByText(/Adds at this position's own leverage: 5x\./)).toBeInTheDocument();
    expect(screen.queryByLabelText('Leverage')).not.toBeInTheDocument();
  });

  it('reduces a short with a buy', async () => {
    renderForm({ positions: [{ ...HELD_LONG, side: 'short' }] });
    await pickMarket();
    enterQuantity('1');
    expect(screen.getByText('Reduces your short position in ETHUSD.')).toBeInTheDocument();
  });
});

describe('OrderForm — reduce only', () => {
  it('blocks a reduce-only order that would open a position', async () => {
    renderForm();
    await pickMarket();
    enterQuantity('1');
    fireEvent.click(screen.getByLabelText('Reduce only'));

    expect(
      screen.getByText(/Reduce-only can only shrink an existing position/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Buy ETHUSD' })).toBeDisabled();
  });

  it('sends reduceOnly for an order that really does reduce', async () => {
    const { onSubmit } = renderForm({ positions: [HELD_LONG] });
    await pickMarket();
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    enterQuantity('1');
    fireEvent.click(screen.getByLabelText('Reduce only'));
    fireEvent.click(screen.getByRole('button', { name: 'Sell ETHUSD' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Sell' }));
    expect(onSubmit.mock.calls[0]![0]).toMatchObject({ side: 'sell', reduceOnly: true });
  });
});

describe('OrderForm — stop-loss and take-profit by side', () => {
  it('describes a long stop as below the price and a short stop as above it', async () => {
    renderForm();
    await pickMarket();
    enterQuantity('1');
    expect(
      screen.getByText('Auto-closes the position if price falls to or below this level.'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    // For a short the stop-loss triggers on a rise and the take-profit on a fall.
    expect(
      screen.getByText('Auto-closes the position if price rises to or above this level.'),
    ).toBeInTheDocument();
  });

  it('clears typed thresholds when the side is switched', async () => {
    renderForm();
    await pickMarket();
    enterQuantity('1');
    fireEvent.change(screen.getByLabelText('Stop-loss price'), { target: { value: '1900' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    expect(screen.getByLabelText('Stop-loss price')).toHaveValue('');
  });

  it('submits thresholds on a short-opening sell', async () => {
    const { onSubmit } = renderForm();
    await pickMarket();
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    enterQuantity('1');
    fireEvent.change(screen.getByLabelText('Stop-loss price'), { target: { value: '2200' } });
    fireEvent.change(screen.getByLabelText('Take-profit price'), { target: { value: '1800' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sell ETHUSD' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Sell' }));
    expect(onSubmit.mock.calls[0]![0]).toMatchObject({
      side: 'sell',
      stopLossPrice: '2200',
      takeProfitPrice: '1800',
    });
  });
});
