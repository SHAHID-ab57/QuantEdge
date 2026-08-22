import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { ThemeProvider } from '@mui/material/styles';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as systemApi from '@/lib/api/system';
import { theme } from '@/theme/theme';
import type { Market } from '@/types/api/market';
import { LiveMarketPage } from './live-market-page';

/**
 * The page keeps its selection in the URL, so the router has to be faked at
 * the module boundary — `next/navigation` needs a mounted App Router that
 * jsdom has no way to provide. `replace` writes back into the same params
 * object the component reads, which is what makes the persistence
 * round-trip observable in a test.
 */
const navigation = vi.hoisted(() => {
  let params = new URLSearchParams();
  const listeners = new Set<() => void>();
  const set = (search: string) => {
    params = new URLSearchParams(search);
    listeners.forEach((listener) => listener());
  };
  return {
    replace: vi.fn((href: string) => set(href.split('?')[1] ?? '')),
    // Identity is stable between writes, as `useSyncExternalStore` requires.
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
    usePathname: () => '/live-market',
    // Subscribed rather than a plain getter: a `replace` has to re-render the
    // page the way the real router does, or nothing downstream would react to
    // a market switch.
    useSearchParams: () =>
      useSyncExternalStore(navigation.subscribe, navigation.read, navigation.read),
  };
});

vi.mock('@/lib/api/system', () => ({
  fetchSystemHealth: vi.fn(),
  fetchSystemStatus: vi.fn(),
  fetchSystemMetrics: vi.fn(),
}));

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
}

function latestSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) {
    throw new Error('no FakeWebSocket instance created yet');
  }
  return socket;
}

const fakeChart = vi.hoisted(() => ({
  addSeries: vi.fn(() => ({
    setData: vi.fn(),
    update: vi.fn(),
    applyOptions: vi.fn(),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
  })),
  applyOptions: vi.fn(),
  remove: vi.fn(),
  timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  subscribeCrosshairMove: vi.fn(),
  unsubscribeCrosshairMove: vi.fn(),
}));

vi.mock('lightweight-charts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lightweight-charts')>();
  return { ...actual, createChart: vi.fn(() => fakeChart) };
});

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchCandlePage: vi.fn(),
  fetchCandleStats: vi.fn(),
}));

const mocked = vi.mocked(marketApi);

/** Alphabetically first, with no candles and no live feed — the exact shape
 * of market that used to be selected by default. */
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
  listing_date: '2024-02-05T12:04:17Z',
};

const markets: Market[] = [
  emptyMarket,
  {
    id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    exchange: 'Delta Exchange',
    exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
    base_asset: 'ETH',
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 3136,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.05',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: '2024-02-05T12:04:17Z',
  },
  {
    id: '11111111-1111-4111-8111-111111111112',
    symbol: 'BTCUSD',
    exchange: 'Delta Exchange',
    exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
    base_asset: 'BTC',
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 27,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.5',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: '2023-12-18T13:10:39Z',
  },
];

function candlePageWithOneCandle(symbol: string, timeframe: string) {
  const items = [
    {
      open_time: '2026-08-22T00:00:00Z',
      close_time: '2026-08-22T00:01:00Z',
      open: '1900',
      high: '1905',
      low: '1895',
      close: '1902',
      volume: '10',
      source: 'delta',
    },
  ];
  return {
    symbol,
    timeframe,
    items,
    pagination: { total: 1, returned: 1, has_more: false, limit: 1000, offset: 0 },
    statistics: {
      highest_price: '1905',
      lowest_price: '1895',
      highest_volume: '10',
      lowest_volume: '10',
      average_open: '1900',
      average_close: '1902',
      average_high: '1905',
      average_low: '1895',
      average_volume: '10',
      total_candles: 1,
      first_candle_at: items[0]!.open_time,
      last_candle_at: items[0]!.open_time,
      expected_candles: 1,
      missing_candles: 0,
      completeness: 100,
    },
    quality: {
      completeness_score: 100,
      freshness_score: 100,
      missing_interval_count: 0,
      missing_intervals: [],
      duplicate_candles: 0,
      out_of_order_candles: 0,
      invalid_ohlc_candles: 0,
      gaps_detected: false,
      overall_quality_score: 100,
    },
    meta: {
      execution_time_ms: 1,
      database_time_ms: 1,
      rows_scanned: 1,
      rows_returned: 1,
      cache_status: 'disabled',
      generated_at: '2026-08-01T00:00:00Z',
    },
  };
}

function candleStats(symbol: string) {
  return {
    symbol,
    timeframe: '5m',
    start: null,
    end: null,
    total_candles: 10,
    highest_price: '2000',
    lowest_price: '1900',
    average_volume: '5',
    first_candle: null,
    last_candle: null,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <LiveMarketPage />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

const mockedSystem = vi.mocked(systemApi);

/** Only the two symbols the backend actually streams have candles/prices. */
const LIVE_PRICES: Record<string, string> = { ETHUSD: '1902', BTCUSD: '77000' };

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

function systemMetrics(latestPrices: Record<string, string> = LIVE_PRICES) {
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

beforeEach(() => {
  FakeWebSocket.instances = [];
  navigation.reset();
  window.localStorage.clear();
  vi.stubGlobal('WebSocket', FakeWebSocket);
  mockedSystem.fetchSystemHealth.mockResolvedValue(systemHealth());
  mockedSystem.fetchSystemStatus.mockResolvedValue(systemStatus());
  mockedSystem.fetchSystemMetrics.mockResolvedValue(systemMetrics());
  mocked.fetchMarkets.mockResolvedValue({ markets, total: markets.length });
  // The empty market has no stored candles; the two tracked ones do.
  mocked.fetchTimeframes.mockImplementation((symbol) =>
    Promise.resolve({
      symbol,
      timeframes: symbol === '1000BONKUSD' ? [] : ['1m', '5m', '1h'],
    }),
  );
  mocked.fetchCandlePage.mockImplementation((symbol, timeframe) =>
    Promise.resolve(candlePageWithOneCandle(symbol, timeframe)),
  );
  mocked.fetchCandleStats.mockImplementation((symbol) => Promise.resolve(candleStats(symbol)));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('LiveMarketPage', () => {
  it('shows a loading state before markets arrive', () => {
    mocked.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(
      screen.getByRole('status', { name: 'Loading live market dashboard' }),
    ).toBeInTheDocument();
  });

  it('shows an error when markets fail to load', async () => {
    mocked.fetchMarkets.mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('network down');
  });

  it('defaults to ETHUSD rather than the alphabetically-first empty market', async () => {
    renderPage();

    // 1000BONKUSD sorts first and has no candles or live feed; it must not win.
    await screen.findByLabelText('ETHUSD live price');
    expect(screen.queryByLabelText('1000BONKUSD live price')).not.toBeInTheDocument();
    expect(
      await screen.findByRole('combobox', { name: 'Select a market for the chart' }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Connecting…').length).toBeGreaterThan(0);
  });

  it('subscribes over the backend gateway and never connects to the exchange', async () => {
    renderPage();
    await screen.findByLabelText('ETHUSD live price');

    const socket = latestSocket();
    expect(socket.url).not.toContain('delta.exchange');
    expect(socket.url).toContain('/api/v1/ws/market');
  });

  it('reflects an open connection and streamed trade in the price card and trade tape', async () => {
    renderPage();
    await screen.findByLabelText('ETHUSD live price');

    act(() => latestSocket().triggerOpen());
    expect((await screen.findAllByText('Connected')).length).toBeGreaterThan(0);

    act(() =>
      latestSocket().triggerMessage({
        type: 'trade',
        symbol: 'ETHUSD',
        data: { price: '1950.5', size: '2', side: 'buy', event_time: '2026-08-22T00:00:00Z' },
      }),
    );

    const priceCard = screen.getByLabelText('ETHUSD live price');
    await waitFor(() => expect(within(priceCard).getByText('1,950.50')).toBeInTheDocument());

    // The same print reaches the tape, tagged with its aggressor side.
    const tape = await screen.findByRole('table', { name: 'Recent trades' });
    expect(within(tape).getByText('Buy')).toBeInTheDocument();
  });

  it('re-subscribes to the new symbol when the market is switched', async () => {
    renderPage();
    await screen.findByLabelText('ETHUSD live price');
    act(() => latestSocket().triggerOpen());

    const marketInput = await screen.findByRole('combobox', {
      name: 'Select a market for the chart',
    });
    fireEvent.mouseDown(marketInput);
    fireEvent.click(await screen.findByRole('option', { name: 'BTCUSD' }));

    await waitFor(() => expect(latestSocket().url).toContain('/api/v1/ws/market'));
    act(() => latestSocket().triggerOpen());
    await waitFor(() => {
      const sent = latestSocket().sent.map((raw) => JSON.parse(raw));
      expect(sent).toContainEqual({ action: 'subscribe', symbols: ['BTCUSD'] });
    });
    expect(await screen.findByLabelText('BTCUSD live price')).toBeInTheDocument();
  });

  it('switches timeframe and refetches candles for the new timeframe', async () => {
    renderPage();
    await screen.findByLabelText('ETHUSD live price');

    const group = await screen.findByRole('group', {
      name: 'Select a timeframe for the chart',
    });
    fireEvent.click(within(group).getByRole('button', { name: '1h' }));

    await waitFor(() =>
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith(
        'ETHUSD',
        '1h',
        expect.objectContaining({ dir: 'desc' }),
      ),
    );
  });

  it('falls back to a valid market when the requested one has no data', async () => {
    navigation.reset('symbol=1000BONKUSD');
    renderPage();

    await screen.findByLabelText('ETHUSD live price');
    expect(await screen.findByLabelText('Market fallback notice')).toHaveTextContent(
      /1000BONKUSD has no research data.*showing ETHUSD instead/,
    );
  });

  it('honours an explicitly requested market that does have data', async () => {
    navigation.reset('symbol=BTCUSD');
    renderPage();

    expect(await screen.findByLabelText('BTCUSD live price')).toBeInTheDocument();
  });

  it('persists the resolved selection to the URL', async () => {
    renderPage();
    await screen.findByLabelText('ETHUSD live price');

    await waitFor(() => {
      expect(navigation.read().get('symbol')).toBe('ETHUSD');
      expect(navigation.read().get('timeframe')).toBe('1m');
    });
  });

  it('restores the market remembered from a previous visit', async () => {
    window.localStorage.setItem('live-market:symbol', 'BTCUSD');
    renderPage();

    expect(await screen.findByLabelText('BTCUSD live price')).toBeInTheDocument();
  });

  it('prefers the finest available timeframe for a live view', async () => {
    renderPage();
    await screen.findByLabelText('ETHUSD live price');

    await waitFor(() =>
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith(
        'ETHUSD',
        '1m',
        expect.objectContaining({ dir: 'desc' }),
      ),
    );
  });

  it('explains why the view is empty when no market has any data', async () => {
    mocked.fetchMarkets.mockResolvedValue({ markets: [emptyMarket], total: 1 });
    mockedSystem.fetchSystemMetrics.mockResolvedValue(systemMetrics({}));
    renderPage();

    const notice = await screen.findByLabelText('Data availability for 1000BONKUSD');
    expect(notice).toHaveTextContent(/No historical candles have been synchronized/);
    expect(notice).toHaveTextContent(/not on the backend live feed/);
    expect(within(notice).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('reports the backend as unreachable when the health endpoint fails', async () => {
    mockedSystem.fetchSystemHealth.mockRejectedValue(new Error('down'));
    renderPage();

    expect(await screen.findByText('Unreachable')).toBeInTheDocument();
  });

  it('shows a reconnecting status after the stream drops', async () => {
    renderPage();
    await screen.findByLabelText('ETHUSD live price');
    act(() => latestSocket().triggerOpen());
    expect((await screen.findAllByText('Connected')).length).toBeGreaterThan(0);

    act(() => latestSocket().close());

    expect((await screen.findAllByText('Reconnecting…')).length).toBeGreaterThan(0);
  });
});
