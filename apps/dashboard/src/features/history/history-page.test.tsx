import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import type { Market } from '@/types/api/market';
import { HistoryPage } from './history-page';

const markets: Market[] = [
  {
    id: '11111111-1111-4111-8111-111111111111',
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
  {
    id: '11111111-1111-4111-8111-111111111112',
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
];

const candles = [
  {
    open_time: '2026-08-01T00:00:00Z',
    close_time: '2026-08-01T01:00:00Z',
    open: '3000',
    high: '3100',
    low: '2950',
    close: '3055.25',
    volume: '120.5',
    source: 'delta',
  },
  {
    open_time: '2026-08-01T01:00:00Z',
    close_time: '2026-08-01T02:00:00Z',
    open: '3055.25',
    high: '3200',
    low: '3040',
    close: '3180.5',
    volume: '85',
    source: 'delta',
  },
];

const pageStatistics = {
  highest_price: '3200',
  lowest_price: '2950',
  highest_volume: '120.5',
  lowest_volume: '85',
  average_open: '3027.63',
  average_close: '3117.88',
  average_high: '3150',
  average_low: '2995',
  average_volume: '102.75',
  total_candles: 5,
  first_candle_at: '2026-08-01T00:00:00Z',
  last_candle_at: '2026-08-01T01:00:00Z',
  expected_candles: 5,
  missing_candles: 0,
  completeness: 100.0,
};

const pageQuality = {
  completeness_score: 100.0,
  freshness_score: 100.0,
  missing_interval_count: 0,
  missing_intervals: [],
  duplicate_candles: 0,
  out_of_order_candles: 0,
  invalid_ohlc_candles: 0,
  gaps_detected: false,
  overall_quality_score: 100.0,
};

const pageMeta = {
  execution_time_ms: 4.2,
  database_time_ms: 3.1,
  rows_scanned: 2,
  rows_returned: 2,
  cache_status: 'disabled',
  generated_at: '2026-08-21T12:00:00Z',
};

const pageResponse = {
  symbol: 'ETHUSD',
  timeframe: '1h',
  items: candles,
  pagination: { total: 5, returned: 2, has_more: true, limit: 100, offset: 0 },
  statistics: pageStatistics,
  quality: pageQuality,
  meta: pageMeta,
};

const zeroedStatistics = {
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
};

const zeroedQuality = {
  completeness_score: 0.0,
  freshness_score: 0.0,
  missing_interval_count: 0,
  missing_intervals: [],
  duplicate_candles: 0,
  out_of_order_candles: 0,
  invalid_ohlc_candles: 0,
  gaps_detected: false,
  overall_quality_score: 0.0,
};

const navigationMock = vi.hoisted(() => ({
  getSearchParams: vi.fn(() => new URLSearchParams()),
  replace: vi.fn(),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchCandlePage: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => navigationMock.getSearchParams(),
  usePathname: () => '/history',
  useRouter: () => ({ replace: navigationMock.replace, push: vi.fn() }),
}));

const mocked = vi.mocked(marketApi);

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <HistoryPage />
    </QueryClientProvider>,
  );
}

async function selectMarketAndTimeframe() {
  const marketInput = await screen.findByRole('combobox', { name: 'Select a market' });
  fireEvent.mouseDown(marketInput);
  fireEvent.change(marketInput, { target: { value: 'ETH' } });
  fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));

  const timeframe = await waitFor(() => {
    const element = screen.getByLabelText('Timeframe');
    const root = element.closest('.MuiInputBase-root') as HTMLElement;
    const control = root.querySelector('input') ?? root;
    expect(control).not.toBeDisabled();
    return element;
  });
  fireEvent.mouseDown(timeframe);
  fireEvent.click(await screen.findByRole('option', { name: '1h' }));
}

async function selectRange(label: string) {
  const range = await screen.findByLabelText('Range');
  fireEvent.mouseDown(range);
  fireEvent.click(await screen.findByRole('option', { name: label }));
}

async function submitQuery() {
  await selectMarketAndTimeframe();
  fireEvent.click(screen.getByRole('button', { name: 'Query' }));
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
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: vi.fn(() => 'blob:mock'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

beforeEach(() => {
  navigationMock.getSearchParams.mockReturnValue(new URLSearchParams());
  mocked.fetchMarkets.mockResolvedValue({ markets, total: markets.length });
  mocked.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1h', '4h'] });
  mocked.fetchCandlePage.mockResolvedValue(pageResponse);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Failed to read blob'));
    reader.readAsText(blob);
  });
}

describe('HistoryPage', () => {
  it('shows a loading skeleton before markets arrive', () => {
    mocked.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading history data' })).toBeInTheDocument();
  });

  it('shows an error state with a retry action', async () => {
    mocked.fetchMarkets.mockRejectedValue(new Error('network down'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load markets');
    expect(alert).toHaveTextContent('network down');

    mocked.fetchMarkets.mockResolvedValue({ markets, total: markets.length });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Select a market' })).toBeInTheDocument();
    });
  });

  it('prompts for a query before any submit', async () => {
    renderPage();
    expect(
      await screen.findByText(
        'Select a market and timeframe, then run a query to explore historical candles.',
      ),
    ).toBeInTheDocument();
  });

  it('runs a query automatically from URL parameters', async () => {
    navigationMock.getSearchParams.mockReturnValue(
      new URLSearchParams('market=ETHUSD&timeframe=1h&limit=100'),
    );
    renderPage();

    await waitFor(() => {
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith('ETHUSD', '1h', {
        limit: 100,
        offset: 0,
        start: undefined,
        end: undefined,
        sort: 'open_time',
        dir: 'asc',
      });
    });
  });

  it('renders candles, statistics, quality, and performance after a query', async () => {
    renderPage();
    await submitQuery();

    await screen.findAllByText('3,055.25');
    expect(screen.getAllByText('3,055.25').length).toBe(2);
    expect(screen.getByText('3,180.50')).toBeInTheDocument();
    expect(screen.getAllByText('120.50').length).toBe(2);
    expect(screen.getAllByText('3,200.00').length).toBe(2);
    expect(screen.getAllByText('2,950.00').length).toBe(2);
    expect(screen.getByText('102.75')).toBeInTheDocument();
    expect(screen.getByText('2 of 5')).toBeInTheDocument();
    expect(screen.getAllByText('100.0 of 100').length).toBe(3);
    expect(screen.getByText('4.2 ms')).toBeInTheDocument();
    expect(screen.getByText(/ETHUSD · 1h · all history/i)).toBeInTheDocument();
  });

  it('converts the custom date range into exclusive UTC bounds', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    await selectRange('Custom Range');
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-08-01' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-08-02' } });
    fireEvent.click(screen.getByRole('button', { name: 'Query' }));

    await waitFor(() => {
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith(
        'ETHUSD',
        '1h',
        expect.objectContaining({
          start: '2026-08-01T00:00:00Z',
          end: '2026-08-03T00:00:00Z',
        }),
      );
    });
    expect(screen.getByText(/2026-08-01T00:00:00Z → 2026-08-03T00:00:00Z/i)).toBeInTheDocument();
  });

  it('resolves a preset range relative to today', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    await selectRange('Last 7 Days');
    fireEvent.click(screen.getByRole('button', { name: 'Query' }));

    await waitFor(() => {
      expect(mocked.fetchCandlePage).toHaveBeenCalled();
    });
    const args = mocked.fetchCandlePage.mock.calls[0]?.[2] as {
      start: string;
      end: string;
    };
    const now = new Date();
    const todayStart = new Date(
      Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
    );
    expect(args.start).toBe(
      new Date(todayStart.getTime() - 6 * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
    );
    const expectedEnd = now.toISOString().replace(/\.\d{3}Z$/, 'Z');
    const delta = Date.parse(args.end) - Date.parse(expectedEnd);
    expect(delta).toBeGreaterThanOrEqual(0);
    expect(delta).toBeLessThan(1000);
  });

  it('paginates with offset', async () => {
    mocked.fetchCandlePage.mockResolvedValue({
      ...pageResponse,
      pagination: { total: 250, returned: 2, has_more: true, limit: 100, offset: 0 },
    });
    renderPage();
    await submitQuery();
    await screen.findAllByText('3,055.25');

    fireEvent.click(screen.getByRole('button', { name: /Go to next page/i }));
    await waitFor(() => {
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith('ETHUSD', '1h', {
        limit: 100,
        offset: 100,
        start: undefined,
        end: undefined,
        sort: 'open_time',
        dir: 'asc',
      });
    });
  });

  it('sorts by column and toggles direction', async () => {
    renderPage();
    await submitQuery();
    await screen.findAllByText('3,055.25');

    fireEvent.click(screen.getByRole('button', { name: 'Volume' }));
    await waitFor(() => {
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith(
        'ETHUSD',
        '1h',
        expect.objectContaining({ sort: 'volume', dir: 'asc' }),
      );
    });

    fireEvent.click(screen.getByRole('button', { name: 'Volume' }));
    await waitFor(() => {
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith(
        'ETHUSD',
        '1h',
        expect.objectContaining({ sort: 'volume', dir: 'desc' }),
      );
    });
  });

  it('copies a cell value and shows feedback', async () => {
    renderPage();
    await submitQuery();
    await screen.findAllByText('3,055.25');

    fireEvent.click(screen.getAllByText('3,055.25')[0] as HTMLElement);

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('3055.25');
    });
    expect(screen.getByRole('status', { name: 'Copied value' })).toHaveTextContent(/3055\.25/);
  });

  it('shows an empty range when the API reports no candles', async () => {
    mocked.fetchCandlePage.mockResolvedValue({
      ...pageResponse,
      items: [],
      pagination: { total: 0, returned: 0, has_more: false, limit: 100, offset: 0 },
      statistics: zeroedStatistics,
      quality: zeroedQuality,
    });
    renderPage();
    await submitQuery();

    expect(await screen.findByRole('status', { name: 'No candles found' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'No statistics available' })).toBeInTheDocument();
    expect(
      screen.getByRole('status', { name: 'No quality metrics available' }),
    ).toBeInTheDocument();
    const csvButton = screen.getByRole('button', { name: 'Export candles as CSV' });
    expect(csvButton).toBeDisabled();
  });

  it('shows an error when the candles query fails', async () => {
    mocked.fetchCandlePage.mockRejectedValue(new Error('boom'));
    renderPage();
    await submitQuery();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load candles');
    expect(alert).toHaveTextContent('boom');
  });

  it('validates that the end date is not before the start date', async () => {
    renderPage();
    await selectMarketAndTimeframe();
    await selectRange('Custom Range');
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-08-02' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-08-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Query' }));

    expect(
      await screen.findByText('End date must be on or after the start date'),
    ).toBeInTheDocument();
    expect(mocked.fetchCandlePage).not.toHaveBeenCalled();
  });

  it('requires a timeframe before querying', async () => {
    renderPage();
    const marketInput = await screen.findByRole('combobox', { name: 'Select a market' });
    fireEvent.mouseDown(marketInput);
    fireEvent.change(marketInput, { target: { value: 'ETH' } });
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.click(screen.getByRole('button', { name: 'Query' }));

    expect(await screen.findByText('Select a timeframe')).toBeInTheDocument();
    expect(mocked.fetchCandlePage).not.toHaveBeenCalled();
  });

  it('syncs the query to the URL', async () => {
    renderPage();
    await submitQuery();
    await screen.findAllByText('3,055.25');

    await waitFor(() => {
      expect(navigationMock.replace).toHaveBeenCalled();
    });
    const href = navigationMock.replace.mock.calls[0]?.[0] as string;
    expect(href).toContain('market=ETHUSD');
    expect(href).toContain('timeframe=1h');
    expect(href).toContain('sort=open_time');
    expect(href).toContain('dir=asc');
    expect(href).not.toContain('page=1');
  });

  it('exports candles as CSV with a metadata block', async () => {
    const createObjectURL = vi.mocked(URL.createObjectURL);
    renderPage();
    await submitQuery();
    await screen.findAllByText('3,055.25');

    fireEvent.click(screen.getByRole('button', { name: 'Export candles as CSV' }));

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalled();
    });
    const blob = createObjectURL.mock.calls[0]?.[0] as Blob;
    const content = await readBlob(blob);
    const lines = content.split('\n');
    expect(lines[0]).toBe('"Key","Value"');
    expect(lines).toContain('"Market","ETHUSD"');
    expect(lines).toContain('"Sort","open_time asc"');
    expect(content).toContain('"Open Time","Open","High","Low","Close","Volume"');
    expect(content).toContain('"2026-08-01T00:00:00Z"');
    expect(content).toContain('"3055.25"');
  });

  it('exports candles as a JSON envelope with backend statistics', async () => {
    const createObjectURL = vi.mocked(URL.createObjectURL);
    renderPage();
    await submitQuery();
    await screen.findAllByText('3,055.25');

    fireEvent.click(screen.getByRole('button', { name: 'Export candles as JSON' }));

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalled();
    });
    const blob = createObjectURL.mock.calls[0]?.[0] as Blob;
    const parsed = JSON.parse(await readBlob(blob)) as {
      market: string;
      candles: unknown[];
      statistics: { total_candles: number };
      quality: { overall_quality_score: number };
    };
    expect(parsed.market).toBe('ETHUSD');
    expect(parsed.candles).toHaveLength(6);
    expect(parsed.statistics.total_candles).toBe(5);
    expect(parsed.quality.overall_quality_score).toBe(100.0);
  });
});
