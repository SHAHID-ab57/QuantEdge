import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as paperTradingApi from '@/lib/api/paper-trading';
import * as systemApi from '@/lib/api/system';
import type {
  PaperAccount,
  PaperAccountListResponse,
  PaperOrder,
  PaperOrderListResponse,
  PaperPositionListResponse,
  PortfolioSummary,
  RiskSummary,
} from '@/types/api/paper-trading';
import { PaperTradingPage } from './paper-trading-page';
import { usePaperTradingAccountStore } from './store/use-paper-trading-account-store';

vi.mock('@/lib/api/paper-trading', () => ({
  createPaperAccount: vi.fn(),
  fetchPaperAccount: vi.fn(),
  fetchPaperAccounts: vi.fn(),
  fetchPaperOrders: vi.fn(),
  fetchPaperPortfolioSummary: vi.fn(),
  fetchPaperPositions: vi.fn(),
  fetchPaperTradingRisk: vi.fn(),
  placePaperOrder: vi.fn(),
  resumePaperTrading: vi.fn(),
  updatePositionThresholds: vi.fn(),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
}));

vi.mock('@/lib/api/system', () => ({
  fetchSystemStatus: vi.fn(),
}));

const mockedPaperTradingApi = vi.mocked(paperTradingApi);
const mockedMarketApi = vi.mocked(marketApi);
const mockedSystemApi = vi.mocked(systemApi);

function account(overrides: Partial<PaperAccount> = {}): PaperAccount {
  return {
    id: 'account-1',
    name: 'My Account',
    starting_balance: '100000',
    balance: '89984.995',
    realized_pnl: '-10.005',
    max_position_size_pct: '10',
    max_exposure_pct: '50',
    max_drawdown_pct: '20',
    peak_balance: '100000',
    trading_halted: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function accountListResponse(
  overrides: Partial<PaperAccountListResponse> = {},
): PaperAccountListResponse {
  return { accounts: [account()], total: 1, limit: 20, offset: 0, ...overrides };
}

function summary(overrides: Partial<PortfolioSummary> = {}): PortfolioSummary {
  return {
    account_id: 'account-1',
    balance: '89984.995',
    realized_pnl: '-10.005',
    unrealized_pnl: '995',
    total_equity: '100979.995',
    open_position_count: 1,
    ...overrides,
  };
}

function positionsResponse(): PaperPositionListResponse {
  return {
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
}

function ordersResponse(overrides: Partial<PaperOrderListResponse> = {}): PaperOrderListResponse {
  return { orders: [], total: 0, limit: 10, offset: 0, ...overrides };
}

function riskSummary(overrides: Partial<RiskSummary> = {}): RiskSummary {
  return {
    account_id: 'account-1',
    balance: '89984.995',
    peak_balance: '100000',
    current_exposure_pct: '11.11',
    max_exposure_pct: '50',
    exposure_headroom_pct: '38.89',
    current_drawdown_pct: '10.015',
    max_drawdown_pct: '20',
    drawdown_headroom_pct: '9.985',
    max_position_size_pct: '10',
    trading_halted: false,
    ...overrides,
  };
}

function order(overrides: Partial<PaperOrder> = {}): PaperOrder {
  return {
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
    trigger_reason: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PaperTradingPage />
    </QueryClientProvider>,
  );
}

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
  mockedSystemApi.fetchSystemStatus.mockResolvedValue({
    status: 'ok',
    started_at: '2026-01-01T00:00:00Z',
    uptime_seconds: 10,
    version: '0.1.0',
    environment: 'development',
    market_data_live: false,
    delta_ws_connected: false,
    delta_ws: null,
    last_ws_message_at: null,
    last_heartbeat_at: null,
    last_ws_reconnect_at: null,
    last_rest_request_at: null,
    last_ingestion_at: null,
    symbols_tracked: 0,
  });
  mockedPaperTradingApi.fetchPaperAccounts.mockResolvedValue(accountListResponse());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  act(() => usePaperTradingAccountStore.getState().setAccountId(null));
  localStorage.clear();
});

describe('PaperTradingPage', () => {
  it('prompts to open an account when none is selected', async () => {
    renderPage();
    expect(await screen.findByText('No paper trading account yet')).toBeInTheDocument();
  });

  it('creates an account and shows its summary', async () => {
    mockedPaperTradingApi.createPaperAccount.mockResolvedValue(account());
    mockedPaperTradingApi.fetchPaperAccount.mockResolvedValue(account());
    mockedPaperTradingApi.fetchPaperPortfolioSummary.mockResolvedValue(summary());
    mockedPaperTradingApi.fetchPaperPositions.mockResolvedValue(positionsResponse());
    mockedPaperTradingApi.fetchPaperOrders.mockResolvedValue(ordersResponse());
    mockedPaperTradingApi.fetchPaperTradingRisk.mockResolvedValue(riskSummary());

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open Account' }));
    const dialogBalance = await screen.findByLabelText('Starting balance');
    fireEvent.change(dialogBalance, { target: { value: '100000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Account' }));

    await waitFor(() =>
      expect(mockedPaperTradingApi.createPaperAccount).toHaveBeenCalledWith({
        name: undefined,
        starting_balance: '100000',
      }),
    );
    expect(await screen.findByText('My Account')).toBeInTheDocument();
  });

  it('places a buy order and refreshes the account view', async () => {
    act(() => usePaperTradingAccountStore.getState().setAccountId('account-1'));
    mockedPaperTradingApi.fetchPaperAccount.mockResolvedValue(account());
    mockedPaperTradingApi.fetchPaperPortfolioSummary.mockResolvedValue(summary());
    mockedPaperTradingApi.fetchPaperPositions.mockResolvedValue(positionsResponse());
    mockedPaperTradingApi.fetchPaperOrders.mockResolvedValue(ordersResponse());
    mockedPaperTradingApi.fetchPaperTradingRisk.mockResolvedValue(riskSummary());
    mockedPaperTradingApi.placePaperOrder.mockResolvedValue(order());

    renderPage();
    await screen.findByText('My Account');

    fireEvent.mouseDown(screen.getByLabelText('Market'));
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buy ETHUSD' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Buy' }));

    await waitFor(() =>
      expect(mockedPaperTradingApi.placePaperOrder).toHaveBeenCalledWith('account-1', {
        symbol: 'ETHUSD',
        side: 'buy',
        quantity: '10',
        stop_loss_price: undefined,
        take_profit_price: undefined,
      }),
    );
  });

  it('places a buy order with a stop-loss and take-profit set', async () => {
    act(() => usePaperTradingAccountStore.getState().setAccountId('account-1'));
    mockedPaperTradingApi.fetchPaperAccount.mockResolvedValue(account());
    mockedPaperTradingApi.fetchPaperPortfolioSummary.mockResolvedValue(summary());
    mockedPaperTradingApi.fetchPaperPositions.mockResolvedValue(positionsResponse());
    mockedPaperTradingApi.fetchPaperOrders.mockResolvedValue(ordersResponse());
    mockedPaperTradingApi.fetchPaperTradingRisk.mockResolvedValue(riskSummary());
    mockedPaperTradingApi.placePaperOrder.mockResolvedValue(order());

    renderPage();
    await screen.findByText('My Account');

    fireEvent.mouseDown(screen.getByLabelText('Market'));
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Stop-loss price'), { target: { value: '900' } });
    fireEvent.change(screen.getByLabelText('Take-profit price'), { target: { value: '1200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buy ETHUSD' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Buy' }));

    await waitFor(() =>
      expect(mockedPaperTradingApi.placePaperOrder).toHaveBeenCalledWith('account-1', {
        symbol: 'ETHUSD',
        side: 'buy',
        quantity: '10',
        stop_loss_price: '900',
        take_profit_price: '1200',
      }),
    );
  });

  it('edits a position’s stop-loss/take-profit from the positions table', async () => {
    act(() => usePaperTradingAccountStore.getState().setAccountId('account-1'));
    mockedPaperTradingApi.fetchPaperAccount.mockResolvedValue(account());
    mockedPaperTradingApi.fetchPaperPortfolioSummary.mockResolvedValue(summary());
    mockedPaperTradingApi.fetchPaperPositions.mockResolvedValue(positionsResponse());
    mockedPaperTradingApi.fetchPaperOrders.mockResolvedValue(ordersResponse());
    mockedPaperTradingApi.fetchPaperTradingRisk.mockResolvedValue(riskSummary());
    mockedPaperTradingApi.updatePositionThresholds.mockResolvedValue({
      ...positionsResponse().positions[0]!,
      stop_loss_price: '950',
    });

    renderPage();
    await screen.findByText('My Account');

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit stop-loss/take-profit for ETHUSD' }),
    );
    const stopLossInput = await screen.findByLabelText('Edit stop-loss price');
    fireEvent.change(stopLossInput, { target: { value: '950' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(mockedPaperTradingApi.updatePositionThresholds).toHaveBeenCalledWith(
        'account-1',
        'ETHUSD',
        { stop_loss_price: '950', take_profit_price: null },
      ),
    );
  });

  it('surfaces a place-order error', async () => {
    act(() => usePaperTradingAccountStore.getState().setAccountId('account-1'));
    mockedPaperTradingApi.fetchPaperAccount.mockResolvedValue(account());
    mockedPaperTradingApi.fetchPaperPortfolioSummary.mockResolvedValue(summary());
    mockedPaperTradingApi.fetchPaperPositions.mockResolvedValue(positionsResponse());
    mockedPaperTradingApi.fetchPaperOrders.mockResolvedValue(ordersResponse());
    mockedPaperTradingApi.fetchPaperTradingRisk.mockResolvedValue(riskSummary());
    mockedPaperTradingApi.placePaperOrder.mockRejectedValue(new Error('insufficient balance'));

    renderPage();
    await screen.findByText('My Account');

    fireEvent.mouseDown(screen.getByLabelText('Market'));
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buy ETHUSD' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Buy' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('insufficient balance');
  });

  it('shows a halted risk panel and resumes trading', async () => {
    act(() => usePaperTradingAccountStore.getState().setAccountId('account-1'));
    mockedPaperTradingApi.fetchPaperAccount.mockResolvedValue(account());
    mockedPaperTradingApi.fetchPaperPortfolioSummary.mockResolvedValue(summary());
    mockedPaperTradingApi.fetchPaperPositions.mockResolvedValue(positionsResponse());
    mockedPaperTradingApi.fetchPaperOrders.mockResolvedValue(ordersResponse());
    mockedPaperTradingApi.fetchPaperTradingRisk.mockResolvedValue(
      riskSummary({ trading_halted: true, current_drawdown_pct: '25' }),
    );
    mockedPaperTradingApi.resumePaperTrading.mockResolvedValue(account());

    renderPage();
    await screen.findByText('My Account');

    expect(await screen.findByText(/Trading halted/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Resume Trading' }));

    // Both the alert's action button and the confirmation dialog's own
    // confirm button share the label "Resume Trading" once the dialog is
    // open — the dialog's is the last one rendered (portalled after it).
    const confirmButtons = await screen.findAllByRole('button', { name: 'Resume Trading' });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]!);

    await waitFor(() =>
      expect(mockedPaperTradingApi.resumePaperTrading).toHaveBeenCalledWith('account-1'),
    );
  });
});
