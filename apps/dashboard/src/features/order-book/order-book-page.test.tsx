import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as systemApi from '@/lib/api/system';
import { theme } from '@/theme/theme';
import type { Market } from '@/types/api/market';
import { OrderBookPage } from './order-book-page';

/** Same fake used by the Live Market Dashboard's page test — see there for why. */
const navigation = vi.hoisted(() => {
  let params = new URLSearchParams();
  const listeners = new Set<() => void>();
  const set = (search: string) => {
    params = new URLSearchParams(search);
    listeners.forEach((listener) => listener());
  };
  return {
    replace: vi.fn((href: string) => set(href.split('?')[1] ?? '')),
    read: () => params,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    reset: (initial = '') => {
      params = new URLSearchParams(initial);
      listeners.clear();
    },
  };
});

vi.mock('next/navigation', async () => {
  const { useSyncExternalStore } = await import('react');
  return {
    useRouter: () => ({ replace: navigation.replace, push: vi.fn(), prefetch: vi.fn() }),
    usePathname: () => '/orderbook',
    useSearchParams: () =>
      useSyncExternalStore(navigation.subscribe, navigation.read, navigation.read),
  };
});

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  triggerOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  triggerMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  triggerServerClose() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}

function latestSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) {
    throw new Error('no FakeWebSocket instance created yet');
  }
  return socket;
}

vi.mock('@/lib/api/market', () => ({ fetchMarkets: vi.fn() }));
vi.mock('@/lib/api/system', () => ({
  fetchSystemHealth: vi.fn(),
  fetchSystemStatus: vi.fn(),
  fetchSystemMetrics: vi.fn(),
}));

const mockedMarket = vi.mocked(marketApi);
const mockedSystem = vi.mocked(systemApi);

const emptyMarket: Market = {
  id: '11111111-1111-4111-8111-111111111110',
  symbol: '1000BONKUSD',
  exchange: 'Delta Exchange',
  exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
  base_asset: '1000BONK',
  quote_asset: 'USD',
  market_type: 'perpetual',
  is_active: true,
  delta_product_id: 9999,
  delta_contract_type: 'perpetual_futures',
  tick_size: '0.0001',
  funding_method: 'mark_price',
  funding_interval_seconds: 28800,
  listing_date: null,
};

function activeMarket(symbol: string): Market {
  return {
    ...emptyMarket,
    id: `11111111-1111-4111-8111-${symbol.padEnd(12, '1').slice(0, 12)}`,
    symbol,
  };
}

const markets: Market[] = [emptyMarket, activeMarket('ETHUSD'), activeMarket('BTCUSD')];

function systemHealth() {
  const component = { name: 'x', status: 'ok' as const, latency_ms: 3 };
  return {
    status: 'ok' as const,
    api: component,
    database: component,
    delta_rest: component,
    delta_ws: component,
    event_bus: component,
    state_manager: component,
  };
}

function systemStatus() {
  return {
    status: 'ok' as const,
    started_at: '2026-08-22T00:00:00Z',
    uptime_seconds: 100,
    version: '0.1.0',
    environment: 'test',
    market_data_live: true,
    delta_ws_connected: true,
    delta_ws: null,
    last_ws_message_at: null,
    last_heartbeat_at: null,
    last_ws_reconnect_at: null,
    last_rest_request_at: null,
    last_ingestion_at: '2026-08-22T00:00:00Z',
    symbols_tracked: 2,
  };
}

function systemMetrics(latestPrices: Record<string, string> = { ETHUSD: '1902', BTCUSD: '77000' }) {
  return {
    collected_at: '2026-08-22T00:00:00Z',
    synchronized_markets: 3,
    stored_candles: 100,
    messages_received: 0,
    messages_normalized: 0,
    validation_failures: 0,
    unsupported_messages: 0,
    events_published: 0,
    average_pipeline_latency_ms: null,
    state_updates: 0,
    invalid_events: 0,
    state_symbols_tracked: Object.keys(latestPrices).length,
    cache_hits: 0,
    cache_misses: 0,
    state_latest_update_at: null,
    state_average_update_latency_ms: null,
    state_order_books_cached: 0,
    state_trades_cached: 0,
    state_tickers_cached: 0,
    state_candles_cached: 0,
    state_latest_prices: latestPrices,
    event_bus_pending: 0,
    event_bus_subscribers: 0,
    event_bus_published: 0,
    event_bus_failed_handlers: 0,
    event_bus_average_handler_latency_ms: null,
  };
}

function orderBookMessage(bids: [string, string][], asks: [string, string][]) {
  return {
    type: 'orderbook',
    symbol: 'ETHUSD',
    data: {
      bids: bids.map(([price, size]) => ({ price, size })),
      asks: asks.map(([price, size]) => ({ price, size })),
      event_time: '2026-08-22T00:00:00Z',
      sequence: 1,
    },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <OrderBookPage />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  navigation.reset();
  window.localStorage.clear();
  vi.stubGlobal('WebSocket', FakeWebSocket);
  mockedSystem.fetchSystemHealth.mockResolvedValue(systemHealth());
  mockedSystem.fetchSystemStatus.mockResolvedValue(systemStatus());
  mockedSystem.fetchSystemMetrics.mockResolvedValue(systemMetrics());
  mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: markets.length });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('OrderBookPage', () => {
  it('shows a loading state before markets arrive', () => {
    mockedMarket.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading order book' })).toBeInTheDocument();
  });

  it('shows an error when markets fail to load', async () => {
    mockedMarket.fetchMarkets.mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('network down');
  });

  it('defaults to ETHUSD rather than the alphabetically-first untracked market', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select a market for the chart' });
    expect(await screen.findByDisplayValue('ETHUSD')).toBeInTheDocument();
  });

  it('subscribes over the backend gateway and never connects to the exchange', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    const socket = latestSocket();
    expect(socket.url).not.toContain('delta.exchange');
    expect(socket.url).toContain('/api/v1/ws/market');
  });

  it('renders bids and asks sorted correctly once an order book update arrives', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    // The gateway always sends bids descending / asks ascending; the
    // frontend trusts that order rather than re-sorting (see
    // `order-book-depth.ts`), so the fixture must match it.
    act(() =>
      latestSocket().triggerMessage(
        orderBookMessage(
          [
            ['100', '1'],
            ['99', '2'],
          ],
          [
            ['101', '2'],
            ['102', '1'],
          ],
        ),
      ),
    );

    const bidsTable = await screen.findByRole('table', { name: 'Order book bids' });
    await waitFor(() => {
      const bidRows = within(bidsTable).getAllByRole('row').slice(1);
      expect(bidRows.length).toBeGreaterThan(0);
      expect(within(bidRows[0]!).getByText('100.00')).toBeInTheDocument(); // best bid first
    });

    const asksTable = screen.getByRole('table', { name: 'Order book asks' });
    const askRows = within(asksTable).getAllByRole('row').slice(1);
    expect(within(askRows[0]!).getByText('101.00')).toBeInTheDocument(); // best ask first
  });

  it('computes and displays the spread from the streamed book', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(orderBookMessage([['100', '1']], [['101', '1']])));

    const spreadPanel = await screen.findByRole('status', { name: 'Order book spread' });
    await waitFor(() => {
      expect(within(spreadPanel).getByText('100.00')).toBeInTheDocument(); // best bid
      expect(within(spreadPanel).getByText('101.00')).toBeInTheDocument(); // best ask
      expect(within(spreadPanel).getByText('1.00')).toBeInTheDocument(); // spread
    });
  });

  it('shows an empty-state notice before any order book snapshot has arrived', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    expect(await screen.findByLabelText('Order book availability for ETHUSD')).toHaveTextContent(
      /Waiting for the ETHUSD order book/,
    );
  });

  it('re-subscribes to the new symbol when the market is switched', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    const marketInput = screen.getByRole('combobox', { name: 'Select a market for the chart' });
    fireEvent.mouseDown(marketInput);
    fireEvent.click(await screen.findByRole('option', { name: 'BTCUSD' }));

    await waitFor(() => expect(latestSocket().url).toContain('/api/v1/ws/market'));
    act(() => latestSocket().triggerOpen());
    await waitFor(() => {
      const sent = latestSocket().sent.map((raw) => JSON.parse(raw));
      expect(sent).toContainEqual({ action: 'subscribe', symbols: ['BTCUSD'] });
    });
  });

  it('switches the visible depth without losing the underlying book', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    const bids: [string, string][] = Array.from({ length: 30 }, (_, i) => [String(200 - i), '1']);
    act(() => latestSocket().triggerMessage(orderBookMessage(bids, [['201', '1']])));

    const bidsTable = await screen.findByRole('table', { name: 'Order book bids' });
    await waitFor(
      () => expect(within(bidsTable).getAllByRole('row')).toHaveLength(26), // header + 25 (default depth)
    );

    fireEvent.click(screen.getByRole('button', { name: '10 levels' }));
    expect(within(bidsTable).getAllByRole('row')).toHaveLength(11); // header + 10

    fireEvent.click(screen.getByRole('button', { name: '100 levels' }));
    expect(within(bidsTable).getAllByRole('row')).toHaveLength(31); // header + all 30 available
  });

  it('shows a reconnecting status after the stream drops', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    expect((await screen.findAllByText('Connected')).length).toBeGreaterThan(0);

    act(() => latestSocket().close());

    expect((await screen.findAllByText('Reconnecting…')).length).toBeGreaterThan(0);
  });

  it('drops an invalid order book payload rather than crashing', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    act(() =>
      latestSocket().triggerMessage({ type: 'orderbook', symbol: 'ETHUSD', data: { bogus: true } }),
    );

    // Still showing the "waiting" notice rather than a crash or stale data.
    expect(await screen.findByLabelText('Order book availability for ETHUSD')).toBeInTheDocument();
  });

  it('explains an untracked market when explicitly requested', async () => {
    navigation.reset('symbol=1000BONKUSD');
    renderPage();
    await screen.findByDisplayValue('1000BONKUSD');
    expect(
      await screen.findByLabelText('Order book availability for 1000BONKUSD'),
    ).toHaveTextContent(/is not on the live feed/);
  });
});
