import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import type { Market, MarketList } from '@/types/api/market';
import { MarketsPage } from './markets-page';

const markets: Market[] = [
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
];

const validList: MarketList = { markets, total: markets.length };

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
}));

const mocked = vi.mocked(marketApi);

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
  mocked.fetchCandlePage.mockResolvedValue({
    symbol: 'ETHUSD',
    timeframe: '1h',
    items: [],
    pagination: { total: 5000, returned: 0, has_more: true, limit: 1, offset: 0 },
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
    expect(screen.getAllByText('just now').length).toBe(2);
  });

  it('applies filters from URL query parameters on first render', async () => {
    navigationMock.setSearchParams(new URLSearchParams('q=eth'));
    renderPage();
    await screen.findByText('ETHUSD');
    expect(screen.queryByText('BTCUSD')).not.toBeInTheDocument();
  });
});
