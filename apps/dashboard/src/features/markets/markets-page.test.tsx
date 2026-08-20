import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as systemApi from '@/lib/api/system';
import type { Market, MarketList } from '@/types/api/market';
import { MarketsPage } from './markets-page';

const withMetadata = (market: Market): Market => ({
  ...market,
  exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
  delta_product_id: 3136,
  delta_contract_type: 'perpetual_futures',
  tick_size: '0.05',
  funding_method: 'mark_price',
  funding_interval_seconds: 28800,
  listing_date: '2024-02-05T12:04:17Z',
});

const markets: Market[] = (
  [
    {
      id: '11111111-1111-1111-1111-111111111101',
      symbol: 'ETHUSD',
      exchange: 'Delta Exchange',
      base_asset: 'ETH',
      quote_asset: 'USD',
      market_type: 'perpetual',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111102',
      symbol: 'BTCUSD',
      exchange: 'Delta Exchange',
      base_asset: 'BTC',
      quote_asset: 'USD',
      market_type: 'perpetual',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111103',
      symbol: 'SOLUSD',
      exchange: 'Delta Exchange',
      base_asset: 'SOL',
      quote_asset: 'USD',
      market_type: 'spot',
      is_active: false,
    },
    {
      id: '11111111-1111-1111-1111-111111111104',
      symbol: 'XRPUSD',
      exchange: 'Delta Exchange',
      base_asset: 'XRP',
      quote_asset: 'USD',
      market_type: 'spot',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111105',
      symbol: 'DOTUSD',
      exchange: 'Delta Exchange',
      base_asset: 'DOT',
      quote_asset: 'USD',
      market_type: 'expiry',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111106',
      symbol: 'ADAUSD',
      exchange: 'Delta Exchange',
      base_asset: 'ADA',
      quote_asset: 'USD',
      market_type: 'spot',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111107',
      symbol: 'AVAXUSD',
      exchange: 'Delta Exchange',
      base_asset: 'AVAX',
      quote_asset: 'USD',
      market_type: 'perpetual',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111108',
      symbol: 'LINKUSD',
      exchange: 'Delta Exchange',
      base_asset: 'LINK',
      quote_asset: 'USD',
      market_type: 'spot',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111109',
      symbol: 'DOGEUSD',
      exchange: 'Delta Exchange',
      base_asset: 'DOGE',
      quote_asset: 'USD',
      market_type: 'spot',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111110',
      symbol: 'MATICUSD',
      exchange: 'CoinGecko',
      base_asset: 'MATIC',
      quote_asset: 'USD',
      market_type: 'spot',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111111',
      symbol: 'NEARUSD',
      exchange: 'Delta Exchange',
      base_asset: 'NEAR',
      quote_asset: 'USD',
      market_type: 'expiry',
      is_active: true,
    },
    {
      id: '11111111-1111-1111-1111-111111111112',
      symbol: 'ARBUSD',
      exchange: 'CoinGecko',
      base_asset: 'ARB',
      quote_asset: 'USD',
      market_type: 'spot',
      is_active: true,
    },
  ] as Market[]
).map(withMetadata);

const validList: MarketList = { markets, total: markets.length };

const emptyCandlePage = {
  symbol: 'ETHUSD',
  timeframe: '1h',
  items: [],
  pagination: { total: 5000, returned: 0, has_more: true, limit: 1, offset: 0 },
  statistics: {
    highest_price: null,
    lowest_price: null,
    highest_volume: null,
    lowest_volume: null,
    average_open: null,
    average_close: null,
    average_high: null,
    average_low: null,
    average_volume: null,
    total_candles: 0,
    first_candle_at: null,
    last_candle_at: null,
    expected_candles: 0,
    missing_candles: 0,
    completeness: null,
  },
  quality: {
    completeness_score: 0.0,
    freshness_score: 0.0,
    missing_interval_count: 0,
    missing_intervals: [],
    duplicate_candles: 0,
    out_of_order_candles: 0,
    invalid_ohlc_candles: 0,
    gaps_detected: false,
    overall_quality_score: 0.0,
  },
  meta: {
    execution_time_ms: 1.0,
    database_time_ms: 0.5,
    rows_scanned: 0,
    rows_returned: 0,
    cache_status: 'disabled',
    generated_at: '2026-08-21T12:00:00Z',
  },
};

const navigationMock = vi.hoisted(() => {
  let searchParams = new URLSearchParams();
  const replace = vi.fn();
  return {
    getSearchParams: () => searchParams,
    setSearchParams: (value: URLSearchParams) => {
      searchParams = value;
    },
    replace,
  };
});

vi.mock('next/navigation', () => ({
  useSearchParams: () => navigationMock.getSearchParams(),
  usePathname: () => '/dashboard/markets',
  useRouter: () => ({ replace: navigationMock.replace, push: vi.fn() }),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchLatestCandle: vi.fn(),
  fetchCandlePage: vi.fn(),
  fetchMarketResearch: vi.fn(),
}));

vi.mock('@/lib/api/system', () => ({
  fetchSystemStatus: vi.fn(),
  fetchSystemHealth: vi.fn(),
  fetchSystemMetrics: vi.fn(),
}));

const mocked = vi.mocked(marketApi);
const mockedSystem = vi.mocked(systemApi);

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MarketsPage />
    </QueryClientProvider>,
  );
}

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

beforeEach(() => {
  navigationMock.setSearchParams(new URLSearchParams());
  mocked.fetchMarkets.mockResolvedValue(validList);
  mocked.fetchTimeframes.mockResolvedValue({
    symbol: 'ETHUSD',
    timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'],
  });
  mocked.fetchLatestCandle.mockResolvedValue({
    symbol: 'ETHUSD',
    timeframe: '1h',
    candle: {
      open_time: '2026-08-19T09:00:00Z',
      close_time: '2999-01-01T00:00:00Z',
      open: '3000',
      high: '3100',
      low: '2950',
      close: '3055.25',
      volume: '120.5',
      source: 'delta',
    },
  });
  mocked.fetchCandlePage.mockResolvedValue(emptyCandlePage);
  mocked.fetchMarketResearch.mockResolvedValue({
    symbol: 'ETHUSD',
    oldest_candle_at: '2026-08-13T00:00:00Z',
    newest_candle_at: '2026-08-20T17:00:00Z',
    coverage_days: 7.7,
    total_candles: 40000,
    timeframes: ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'].map((timeframe) => ({
      timeframe,
      stored_candles: 5000,
      oldest_at: '2026-08-13T00:00:00Z',
      newest_at: '2026-08-20T17:00:00Z',
      coverage_days: 7.0,
      expected_candles: 5000,
      missing_candles: 0,
      completeness: 100,
      average_daily_candles: 714.3,
    })),
  });
  mockedSystem.fetchSystemStatus.mockResolvedValue({
    status: 'ok',
    started_at: '2026-08-20T10:00:00Z',
    uptime_seconds: 3600,
    version: '1.0.0',
    environment: 'test',
    market_data_live: true,
    delta_ws_connected: true,
    delta_ws: null,
    last_ws_message_at: '2026-08-20T17:30:00Z',
    last_heartbeat_at: null,
    last_ws_reconnect_at: null,
    last_rest_request_at: null,
    last_ingestion_at: null,
    symbols_tracked: 2,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  navigationMock.replace.mockClear();
});

describe('MarketsPage', () => {
  it('shows a loading skeleton before data arrives', () => {
    mocked.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading markets' })).toBeInTheDocument();
  });

  it('shows an error state with a retry action', async () => {
    mocked.fetchMarkets.mockRejectedValue(new Error('network down'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load markets');
    expect(alert).toHaveTextContent('network down');

    mocked.fetchMarkets.mockResolvedValue(validList);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    });
  });

  it('shows an empty state when no markets exist', async () => {
    mocked.fetchMarkets.mockResolvedValue({ markets: [], total: 0 });
    renderPage();
    expect(await screen.findByText('No markets available')).toBeInTheDocument();
  });

  it('renders markets from the API', async () => {
    renderPage();
    expect(await screen.findByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getAllByText('Delta Exchange').length).toBeGreaterThan(0);
    expect(screen.getAllByText('perpetual').length).toBe(3);
    expect(screen.getByText('12 of 12 markets match the current filters.')).toBeInTheDocument();
  });

  it('filters rows by search input', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.change(screen.getByRole('textbox', { name: /Search symbols/i }), {
      target: { value: 'eth' },
    });
    await waitFor(() => {
      expect(screen.getByText('ETHUSD')).toBeInTheDocument();
      expect(screen.queryByText('BTCUSD')).not.toBeInTheDocument();
    });
    expect(screen.getByText('1 of 12 markets match the current filters.')).toBeInTheDocument();
  });

  it('debounces the search into the URL query parameter', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.change(screen.getByRole('textbox', { name: /Search symbols/i }), {
      target: { value: 'sol' },
    });
    await waitFor(() => {
      expect(navigationMock.replace).toHaveBeenCalledWith(
        expect.stringContaining('q=sol'),
        expect.anything(),
      );
    });
  });

  it('filters rows by status', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    fireEvent.click(await screen.findByRole('option', { name: 'Active' }));
    await waitFor(() => {
      expect(screen.queryByText('SOLUSD')).not.toBeInTheDocument();
      expect(screen.getByText('11 of 12 markets match the current filters.')).toBeInTheDocument();
    });
  });

  it('filters rows by market type', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.mouseDown(screen.getByLabelText('Market Type'));
    fireEvent.click(await screen.findByRole('option', { name: 'expiry' }));
    await waitFor(() => {
      expect(screen.getByText('DOTUSD')).toBeInTheDocument();
      expect(screen.queryByText('ETHUSD')).not.toBeInTheDocument();
    });
  });

  it('filters rows by exchange', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.mouseDown(screen.getByLabelText('Exchange'));
    fireEvent.click(await screen.findByRole('option', { name: 'CoinGecko' }));
    await waitFor(() => {
      expect(screen.getByText('MATICUSD')).toBeInTheDocument();
      expect(screen.queryByText('ETHUSD')).not.toBeInTheDocument();
    });
  });

  it('clears all filters', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.change(screen.getByRole('textbox', { name: /Search symbols/i }), {
      target: { value: 'eth' },
    });
    await waitFor(() => {
      expect(screen.queryByText('BTCUSD')).not.toBeInTheDocument();
    });
    const clearButton = await screen.findByRole('button', { name: /Clear filters/i });
    fireEvent.click(clearButton);
    await waitFor(() => {
      expect(screen.getByText('BTCUSD')).toBeInTheDocument();
    });
  });

  it('sorts rows by column header', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    const header = screen.getByRole('columnheader', { name: /Symbol/i });
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    fireEvent.click(screen.getByText('Symbol'));
    await waitFor(() => {
      expect(screen.getByRole('columnheader', { name: /Symbol/i })).toHaveAttribute(
        'aria-sort',
        'descending',
      );
    });
    const firstRow = screen.getAllByRole('row')[1];
    expect(firstRow).toHaveTextContent('XRPUSD');
  });

  it('paginates rows', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    expect(screen.queryByText('SOLUSD')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Go to next page/i }));
    await waitFor(() => {
      expect(screen.getByText('SOLUSD')).toBeInTheDocument();
    });
  });

  it('shows market details when a row is selected', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    expect(mocked.fetchTimeframes).toHaveBeenCalledWith('ETHUSD');
    expect(await screen.findByText('3,055.25')).toBeInTheDocument();
    expect(screen.getByText('40,000')).toBeInTheDocument();
    expect(screen.getByText('Good')).toBeInTheDocument();
    expect(screen.getByText('50/50 · 100%')).toBeInTheDocument();
    expect(screen.getByText('30/30 · 100%')).toBeInTheDocument();
    expect(screen.getByText('15/20 · 75%')).toBeInTheDocument();
    const recommendations = screen.getByRole('region', {
      name: 'Data quality recommendations',
    });
    expect(recommendations).toHaveTextContent('Data is current and complete');
  });

  it('explains the data quality breakdown for a thin and stale market', async () => {
    const staleClose = new Date(Date.now() - 2 * 3_600_000).toISOString();
    mocked.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1h'] });
    mocked.fetchLatestCandle.mockResolvedValue({
      symbol: 'ETHUSD',
      timeframe: '1h',
      candle: {
        open_time: new Date(Date.now() - 3 * 3_600_000).toISOString(),
        close_time: staleClose,
        open: '3000',
        high: '3100',
        low: '2950',
        close: '3055.25',
        volume: '120.5',
        source: 'delta',
      },
    });
    mocked.fetchCandlePage.mockResolvedValue({
      ...emptyCandlePage,
      pagination: { total: 137, returned: 0, has_more: false, limit: 1, offset: 0 },
    });
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    expect(await screen.findByText('49/100')).toBeInTheDocument();
    expect(screen.getByText('Poor')).toBeInTheDocument();
    expect(screen.getByText('40/50 · 80%')).toBeInTheDocument();
    expect(screen.getByText('4/30 · 13%')).toBeInTheDocument();
    expect(screen.getByText('5/20 · 25%')).toBeInTheDocument();
    const recommendations = screen.getByRole('region', {
      name: 'Data quality recommendations',
    });
    expect(recommendations).toHaveTextContent(
      'Enable additional timeframes: 1m, 5m, 15m, 30m, 4h, 1d, 1w',
    );
    expect(recommendations).toHaveTextContent(
      'Synchronize additional historical candles (backfill)',
    );
    expect(recommendations).toHaveTextContent('ensure the candle sync scheduler is running');
    expect(recommendations).toHaveTextContent('Latest candle is 2h old');
    expect(
      screen.getByText(
        'Deductions: Latest candle freshness −10, Timeframe coverage −26, Stored candle volume −15',
      ),
    ).toBeInTheDocument();
  });

  it('applies filters from URL query parameters on first render', async () => {
    navigationMock.setSearchParams(new URLSearchParams('q=eth'));
    renderPage();
    await screen.findByText('ETHUSD');
    expect(screen.queryByText('BTCUSD')).not.toBeInTheDocument();
  });

  it('shows contract metadata sourced from the API', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    await screen.findByText('0.05');
    const panel = screen.getByRole('region', { name: /Details for ETHUSD/i });

    expect(panel).toHaveTextContent('Exchange ID');
    expect(panel).toHaveTextContent('6b698660');
    expect(panel).toHaveTextContent('Symbol ID');
    expect(panel).toHaveTextContent('3136');
    expect(panel).toHaveTextContent('Tick size');
    expect(panel).toHaveTextContent('0.05');
    expect(panel).toHaveTextContent('Contract type');
    expect(panel).toHaveTextContent('perpetual_futures');
    expect(panel).toHaveTextContent('Every 8h · mark_price');
    expect(panel).toHaveTextContent('Listing date');
    expect(panel).toHaveTextContent('2024');
    expect(panel).toHaveTextContent(
      'Contract size, price precision, and quantity precision are not published by Delta Exchange.',
    );
  });

  it('indicates the live data source and last update', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    const status = await screen.findByRole('status', { name: 'Live status' });

    await waitFor(() => {
      expect(status).toHaveTextContent('Live WebSocket');
    });
    expect(status).toHaveTextContent('Historical database');
    expect(status).toHaveTextContent('Prices updated');
    expect(status).toHaveTextContent('WebSocket feed');
    expect(status).toHaveTextContent('Connected');
    expect(status).toHaveTextContent('Synchronization');
  });

  it('shows an Updating state while the WebSocket feed is fresh', async () => {
    mockedSystem.fetchSystemStatus.mockResolvedValue({
      status: 'ok',
      started_at: '2026-08-20T10:00:00Z',
      uptime_seconds: 3600,
      version: '1.0.0',
      environment: 'test',
      market_data_live: true,
      delta_ws_connected: true,
      delta_ws: null,
      last_ws_message_at: new Date().toISOString(),
      last_heartbeat_at: null,
      last_ws_reconnect_at: null,
      last_rest_request_at: null,
      last_ingestion_at: null,
      symbols_tracked: 2,
    });
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    const status = await screen.findByRole('status', { name: 'Live status' });
    await waitFor(() => {
      expect(status).toHaveTextContent('Updating');
    });
  });

  it('shows a Disconnected state and REST snapshot when the WebSocket is down', async () => {
    mockedSystem.fetchSystemStatus.mockResolvedValue({
      status: 'ok',
      started_at: '2026-08-20T10:00:00Z',
      uptime_seconds: 3600,
      version: '1.0.0',
      environment: 'test',
      market_data_live: true,
      delta_ws_connected: false,
      delta_ws: null,
      last_ws_message_at: null,
      last_heartbeat_at: null,
      last_ws_reconnect_at: null,
      last_rest_request_at: null,
      last_ingestion_at: null,
      symbols_tracked: 2,
    });
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    const status = await screen.findByRole('status', { name: 'Live status' });
    await waitFor(() => {
      expect(status).toHaveTextContent('REST snapshot');
    });
    expect(status).toHaveTextContent('Disconnected');
  });

  it('shows research metrics for the selected timeframe', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    await screen.findByText('Research metrics · 1h');
    const panel = screen.getByRole('region', { name: /Details for ETHUSD/i });

    expect(panel).toHaveTextContent('Research metrics · 1h');
    expect(panel).toHaveTextContent('Oldest candle');
    expect(panel).toHaveTextContent('Newest candle');
    expect(panel).toHaveTextContent('Coverage duration');
    expect(panel).toHaveTextContent('7.0d');
    expect(panel).toHaveTextContent('Missing candles');
    expect(panel).toHaveTextContent('Data completeness');
    expect(panel).toHaveTextContent('100.0%');
    expect(panel).toHaveTextContent('Average daily candles');
    expect(panel).toHaveTextContent('714.3');
  });

  it('switches the research metrics when a timeframe is selected', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    await screen.findByText('Research metrics · 1h');
    const panel = screen.getByRole('region', { name: /Details for ETHUSD/i });

    fireEvent.click(screen.getByRole('button', { name: 'Timeframe 5m, 5,000 candles' }));
    await waitFor(() => {
      expect(panel).toHaveTextContent('Research metrics · 5m');
    });
    expect(screen.getByRole('button', { name: 'Timeframe 5m, 5,000 candles' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('recalculates the quality score from fresh data', async () => {
    renderPage();
    await screen.findByText('ETHUSD');
    fireEvent.click(screen.getByText('ETHUSD'));
    await screen.findByText('95/100');
    expect(screen.getByText('Deductions: Stored candle volume −5')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Recalculate data quality score' }));

    await waitFor(() => {
      expect(mocked.fetchTimeframes).toHaveBeenCalledTimes(2);
    });
  });

  it('selects a market with the keyboard', async () => {
    renderPage();
    const row = (await screen.findByText('ETHUSD')).closest('tr');
    expect(row).not.toBeNull();
    fireEvent.keyDown(row as HTMLElement, { key: 'Enter' });
    expect(await screen.findByText('95/100')).toBeInTheDocument();
  });
});
