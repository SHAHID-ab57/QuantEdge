import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import { ApiError } from '@/lib/api/errors';
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

const pageResponse = {
  symbol: 'ETHUSD',
  timeframe: '1h',
  items: candles,
  pagination: { total: 5, returned: 2, has_more: true, limit: 100, offset: 0 },
};

const statsResponse = {
  symbol: 'ETHUSD',
  timeframe: '1h',
  start: null,
  end: null,
  total_candles: 5,
  highest_price: '3200',
  lowest_price: '2950',
  average_volume: '102.75',
  first_candle: candles[0] ?? null,
  last_candle: candles[1] ?? null,
};

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchCandlePage: vi.fn(),
  fetchCandleStats: vi.fn(),
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
});

beforeEach(() => {
  mocked.fetchMarkets.mockResolvedValue({ markets, total: markets.length });
  mocked.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1h', '4h'] });
  mocked.fetchCandlePage.mockResolvedValue(pageResponse);
  mocked.fetchCandleStats.mockResolvedValue(statsResponse);
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

  it('renders candles, statistics, and performance after a query', async () => {
    renderPage();
    await submitQuery();

    await screen.findAllByText('3,055.25');
    expect(screen.getAllByText('3,055.25').length).toBe(2);
    expect(screen.getByText('3,180.50')).toBeInTheDocument();
    expect(screen.getByText('120.50')).toBeInTheDocument();
    expect(screen.getAllByText('3,200.00').length).toBe(2);
    expect(screen.getAllByText('2,950.00').length).toBe(2);
    expect(screen.getByText('102.75')).toBeInTheDocument();
    expect(screen.getByText('2 of 5')).toBeInTheDocument();
    expect(screen.getByText(/ETHUSD · 1h · all history/i)).toBeInTheDocument();
  });

  it('converts the date range into exclusive UTC bounds', async () => {
    renderPage();
    await selectMarketAndTimeframe();
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

  it('paginates with offset', async () => {
    mocked.fetchCandlePage.mockResolvedValue({
      symbol: 'ETHUSD',
      timeframe: '1h',
      items: candles,
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
      });
    });
  });

  it('shows an empty range when the stats endpoint reports no data', async () => {
    mocked.fetchCandlePage.mockResolvedValue({
      symbol: 'ETHUSD',
      timeframe: '1h',
      items: [],
      pagination: { total: 0, returned: 0, has_more: false, limit: 100, offset: 0 },
    });
    mocked.fetchCandleStats.mockRejectedValue(
      new ApiError(404, 'HTTP_404', 'No candles stored for market'),
    );
    renderPage();
    await submitQuery();

    expect(await screen.findByRole('status', { name: 'No candles found' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'No statistics available' })).toBeInTheDocument();
    const csvButton = screen.getByRole('button', { name: 'Export candles as CSV' });
    expect(csvButton).toBeDisabled();
  });

  it('shows an error when the candles query fails', async () => {
    mocked.fetchCandlePage.mockRejectedValue(new ApiError(500, 'HTTP_500', 'boom'));
    renderPage();
    await submitQuery();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load candles');
    expect(alert).toHaveTextContent('boom');
  });

  it('validates that the end date is not before the start date', async () => {
    renderPage();
    await selectMarketAndTimeframe();
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

  it('exports candles as CSV with proper headers', async () => {
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
    expect(content.split('\n')[0]).toBe('Open Time,Open,High,Low,Close,Volume');
    expect(content).toContain('"2026-08-01T00:00:00Z"');
    expect(content).toContain('"3055.25"');
  });

  it('exports candles as JSON', async () => {
    const createObjectURL = vi.mocked(URL.createObjectURL);
    renderPage();
    await submitQuery();
    await screen.findAllByText('3,055.25');

    fireEvent.click(screen.getByRole('button', { name: 'Export candles as JSON' }));

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalled();
    });
    const blob = createObjectURL.mock.calls[0]?.[0] as Blob;
    const parsed = JSON.parse(await readBlob(blob)) as Array<{ symbol: string }>;
    expect(parsed).toHaveLength(6);
  });
});
