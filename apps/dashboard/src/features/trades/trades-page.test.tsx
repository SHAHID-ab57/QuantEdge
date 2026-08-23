import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as systemApi from '@/lib/api/system';
import { theme } from '@/theme/theme';
import type { Market } from '@/types/api/market';
import { TradesPage } from './trades-page';

/** Same fake used by the Order Book/Live Market page tests — see there for why. */
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
    usePathname: () => '/trades',
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

/**
 * Reads the value rendered next to a `StatTile`'s label, scoped within
 * `container` — several tiles can legitimately show the same numeral
 * (e.g. buy volume and trade count both being `2`), so a bare
 * `getByText` risks an ambiguous match; this instead walks from the
 * unambiguous label to its own value.
 */
function tileValue(container: HTMLElement, label: string): string | null {
  const labelNode = within(container).getByText(label);
  // Climb from the label to the nearest ancestor that actually holds a value
  // node. The label now sits inside its own row alongside a `MetricInfo`
  // button, so the tile is not necessarily the label's direct parent.
  let node: HTMLElement | null = labelNode.parentElement;
  while (node && !node.querySelector('p')) {
    node = node.parentElement;
  }
  return node?.querySelector('p')?.textContent ?? null;
}

function tradeMessage(price: string, size: string, side: string) {
  return {
    type: 'trade',
    symbol: 'ETHUSD',
    data: { price, size, side, event_time: new Date().toISOString() },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <TradesPage />
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

describe('TradesPage', () => {
  it('shows a loading state before markets arrive', () => {
    mockedMarket.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading trade analytics' })).toBeInTheDocument();
  });

  it('shows an error when markets fail to load', async () => {
    mockedMarket.fetchMarkets.mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('network down');
  });

  it('defaults to ETHUSD rather than the alphabetically-first untracked market', async () => {
    renderPage();
    expect(await screen.findByDisplayValue('ETHUSD')).toBeInTheDocument();
  });

  it('subscribes over the backend gateway and never connects to the exchange', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    const socket = latestSocket();
    expect(socket.url).not.toContain('delta.exchange');
    expect(socket.url).toContain('/api/v1/ws/market');
  });

  it('shows an empty-state notice before any trade has arrived', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    expect(
      await screen.findByLabelText('Trade analytics availability for ETHUSD'),
    ).toHaveTextContent(/Waiting for the first ETHUSD trade/);
  });

  it('renders a streamed trade in the tape with time, price, quantity, side, and value', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    act(() => latestSocket().triggerMessage(tradeMessage('100', '2', 'buy')));

    const tape = await screen.findByRole('table', { name: 'Recent trades' });
    await waitFor(() => {
      expect(within(tape).getByText('100.00')).toBeInTheDocument();
      expect(within(tape).getByText('2.00')).toBeInTheDocument();
      expect(within(tape).getByText('Buy')).toBeInTheDocument();
      expect(within(tape).getByText('200.00')).toBeInTheDocument(); // trade value = 100 * 2
    });
  });

  it('updates statistics, VWAP, and rolling analytics from streamed trades', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    // Distinct sizes so buy/sell/total/count/average never coincidentally
    // collide on the same rendered numeral.
    act(() => latestSocket().triggerMessage(tradeMessage('100', '4', 'buy')));
    act(() => latestSocket().triggerMessage(tradeMessage('100', '6', 'sell')));

    const statsPanel = await screen.findByRole('status', { name: 'Trade statistics' });
    await waitFor(() => {
      expect(tileValue(statsPanel, 'Buy Volume')).toBe('4');
      expect(tileValue(statsPanel, 'Sell Volume')).toBe('6');
      expect(tileValue(statsPanel, 'Total Volume')).toBe('10');
      expect(tileValue(statsPanel, 'Number of Trades')).toBe('2');
    });

    const vwapPanel = screen.getByRole('status', { name: 'VWAP' });
    expect(tileValue(vwapPanel, 'Session VWAP')).toBe('100.00');

    const rollingPanel = screen.getByRole('status', { name: 'Rolling analytics (last minute)' });
    expect(tileValue(rollingPanel, 'Trades / Minute')).toBe('2');
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

  it('resets statistics when the market is switched', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('100', '5', 'buy')));

    const statsPanel = await screen.findByRole('status', { name: 'Trade statistics' });
    await waitFor(() => expect(tileValue(statsPanel, 'Number of Trades')).toBe('1'));

    const marketInput = screen.getByRole('combobox', { name: 'Select a market for the chart' });
    fireEvent.mouseDown(marketInput);
    fireEvent.click(await screen.findByRole('option', { name: 'BTCUSD' }));

    await waitFor(() => expect(screen.getByDisplayValue('BTCUSD')).toBeInTheDocument());
    expect(tileValue(statsPanel, 'Number of Trades')).toBe('0');
  });

  it('changes the tape row cap via the max-rows selector', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    fireEvent.click(screen.getByRole('button', { name: '25 rows' }));

    expect(screen.getByText('newest first · last 25')).toBeInTheDocument();
  });

  it('shows a reconnecting status after the stream drops', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    expect((await screen.findAllByText('Connected')).length).toBeGreaterThan(0);

    act(() => latestSocket().close());

    expect((await screen.findAllByText('Reconnecting…')).length).toBeGreaterThan(0);
  });

  it('drops an invalid trade payload rather than crashing', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    act(() =>
      latestSocket().triggerMessage({ type: 'trade', symbol: 'ETHUSD', data: { bogus: true } }),
    );

    // Still showing the "waiting" notice rather than a crash or stale data.
    expect(
      await screen.findByLabelText('Trade analytics availability for ETHUSD'),
    ).toBeInTheDocument();
  });

  it('explains an untracked market when explicitly requested', async () => {
    navigation.reset('symbol=1000BONKUSD');
    renderPage();
    await screen.findByDisplayValue('1000BONKUSD');
    expect(
      await screen.findByLabelText('Trade analytics availability for 1000BONKUSD'),
    ).toHaveTextContent(/is not on the live feed/);
  });

  it('derives a Bullish market sentiment chip from one-sided buying', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('100', '10', 'buy')));

    const sentimentPanel = await screen.findByRole('status', { name: 'Market sentiment' });
    await waitFor(() =>
      expect(within(sentimentPanel).getByText('Strongly Bullish')).toBeInTheDocument(),
    );
  });

  it('shows dedicated session and last-minute Largest Trade cards with full detail', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('500', '2', 'buy'))); // value 1000

    expect(await screen.findByText('Largest Trade — Session')).toBeInTheDocument();
    expect(screen.getByText('Largest Trade — Last Minute')).toBeInTheDocument();
    await waitFor(() => {
      // Both Largest Trade cards, plus the same trade's own Trade Value cell in the tape.
      expect(screen.getAllByText('1,000.00')).toHaveLength(3);
    });
  });

  it('filters the trade tape to Buy-only when the Buy filter is selected, without affecting statistics', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('100', '1', 'buy')));
    act(() => latestSocket().triggerMessage(tradeMessage('200', '1', 'sell')));

    const tape = await screen.findByRole('table', { name: 'Recent trades' });
    await waitFor(() => expect(within(tape).getAllByRole('row')).toHaveLength(3)); // header + 2 trades

    fireEvent.click(screen.getByRole('button', { name: 'Show Buy trades' }));

    await waitFor(() => expect(within(tape).getAllByRole('row')).toHaveLength(2)); // header + 1 buy trade

    const statsPanel = screen.getByRole('status', { name: 'Trade statistics' });
    // The filter is display-only — session stats still reflect both trades.
    expect(tileValue(statsPanel, 'Number of Trades')).toBe('2');
  });

  it('filters the trade tape by minimum size', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('100', '1', 'buy')));
    act(() => latestSocket().triggerMessage(tradeMessage('100', '50', 'buy')));

    const tape = await screen.findByRole('table', { name: 'Recent trades' });
    await waitFor(() => expect(within(tape).getAllByRole('row')).toHaveLength(3));

    fireEvent.change(screen.getByLabelText('Minimum trade size'), { target: { value: '10' } });

    await waitFor(() => expect(within(tape).getAllByRole('row')).toHaveLength(2));
    expect(within(tape).getByText('50.00')).toBeInTheDocument();
  });

  it('shows current price, session high/low, and VWAP distance in the primary band', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('100', '1', 'buy')));
    act(() => latestSocket().triggerMessage(tradeMessage('120', '1', 'buy')));

    const header = await screen.findByRole('status', { name: 'ETHUSD price summary' });
    await waitFor(() => {
      expect(tileValue(header, 'Session High')).toBe('120.00');
      expect(tileValue(header, 'Session Low')).toBe('100.00');
    });
    // Session VWAP is 110, last price is 120 → +9.09% above VWAP.
    expect(tileValue(header, 'vs VWAP')).toBe('+9.09%');
  });

  it('groups metrics into labelled sections rather than one flat run of panels', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    for (const name of ['Order Flow', 'VWAP', 'Session Statistics', 'Connection']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
  });

  it('offers a contextual explanation beside every metric on the page', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    // One representative metric from each section, all reachable by keyboard.
    for (const label of [
      'About Current Price',
      'About Market Sentiment',
      'About Trades per Minute',
      'About Trade Size Distribution',
      'About Session VWAP',
      'About Buy Volume',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });

  it('shows a trade size distribution over the last minute', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('100', '1', 'buy')));

    await waitFor(() => expect(screen.getByText('1 trades')).toBeInTheDocument());
    expect(screen.getAllByRole('meter', { name: /of average size/ })).toHaveLength(5);
  });

  it('reports how many tape rows a filter is hiding', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeMessage('100', '1', 'buy')));
    act(() => latestSocket().triggerMessage(tradeMessage('200', '1', 'sell')));

    await waitFor(() =>
      expect(screen.getByLabelText('Trade tape filter result')).toHaveTextContent(
        'Showing all 2 rows',
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show Buy trades' }));

    await waitFor(() =>
      expect(screen.getByLabelText('Trade tape filter result')).toHaveTextContent(
        'Showing 1 of 2 rows',
      ),
    );
  });

  it('enables the CSV export only once there are visible rows to export', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());

    const exportButton = screen.getByRole('button', {
      name: 'Export visible trade tape rows as CSV',
    });
    expect(exportButton).toBeDisabled();

    act(() => latestSocket().triggerMessage(tradeMessage('100', '1', 'buy')));

    await waitFor(() => expect(exportButton).toBeEnabled());
  });

  it('highlights an unusually large trade in the tape once a session baseline exists', async () => {
    renderPage();
    await screen.findByDisplayValue('ETHUSD');
    act(() => latestSocket().triggerOpen());
    // Baseline average notional established by several small trades...
    for (let i = 0; i < 5; i += 1) {
      act(() => latestSocket().triggerMessage(tradeMessage('10', '1', 'buy'))); // value 10
    }
    // ...then one far larger than 5x that baseline.
    act(() => latestSocket().triggerMessage(tradeMessage('10', '1000', 'buy'))); // value 10,000

    await waitFor(() => expect(screen.getByText('Large')).toBeInTheDocument());
  });
});
