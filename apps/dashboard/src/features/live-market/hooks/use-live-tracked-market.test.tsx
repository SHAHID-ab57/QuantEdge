import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as systemApi from '@/lib/api/system';
import type { Market, MarketList } from '@/types/api/market';
import type { SystemMetrics } from '@/types/api/system';
import { useLiveTrackedMarket } from './use-live-tracked-market';

vi.mock('@/lib/api/market', () => ({ fetchMarkets: vi.fn() }));
vi.mock('@/lib/api/system', () => ({ fetchSystemMetrics: vi.fn() }));

const mockedMarket = vi.mocked(marketApi);
const mockedSystem = vi.mocked(systemApi);

function market(symbol: string): Market {
  return {
    id: `11111111-1111-4111-8111-${symbol.padEnd(12, '0').slice(0, 12)}`,
    symbol,
    exchange: 'Delta Exchange',
    exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
    base_asset: symbol.replace('USD', ''),
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 1,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.05',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: null,
  };
}

function markets(symbols: string[]): MarketList {
  return { markets: symbols.map(market), total: symbols.length };
}

function metrics(latestPrices: Record<string, string>): SystemMetrics {
  return {
    collected_at: '2026-08-22T00:00:00Z',
    synchronized_markets: null,
    stored_candles: null,
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

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useLiveTrackedMarket', () => {
  it('resolves to ETHUSD rather than the alphabetically-first untracked market', async () => {
    mockedMarket.fetchMarkets.mockResolvedValue(markets(['1000BONKUSD', 'ETHUSD', 'BTCUSD']));
    mockedSystem.fetchSystemMetrics.mockResolvedValue(metrics({ ETHUSD: '1900', BTCUSD: '70000' }));

    const { result } = renderHook(() => useLiveTrackedMarket(null, null), { wrapper });

    await waitFor(() => expect(result.current.symbol).toBe('ETHUSD'));
    expect(result.current.isUntracked).toBe(false);
  });

  it('honours an explicitly requested market even if untracked, flagging it as such', async () => {
    mockedMarket.fetchMarkets.mockResolvedValue(markets(['1000BONKUSD', 'ETHUSD']));
    mockedSystem.fetchSystemMetrics.mockResolvedValue(metrics({ ETHUSD: '1900' }));

    const { result } = renderHook(() => useLiveTrackedMarket('1000BONKUSD', null), { wrapper });

    await waitFor(() => expect(result.current.symbol).toBe('1000BONKUSD'));
    expect(result.current.isUntracked).toBe(true);
  });

  it('restores the remembered market when nothing is requested', async () => {
    mockedMarket.fetchMarkets.mockResolvedValue(markets(['ETHUSD', 'BTCUSD']));
    mockedSystem.fetchSystemMetrics.mockResolvedValue(metrics({ ETHUSD: '1900', BTCUSD: '70000' }));

    const { result } = renderHook(() => useLiveTrackedMarket(null, 'BTCUSD'), { wrapper });

    await waitFor(() => expect(result.current.symbol).toBe('BTCUSD'));
  });

  it('reports resolving while markets are still loading', () => {
    mockedMarket.fetchMarkets.mockReturnValue(new Promise(() => undefined));
    mockedSystem.fetchSystemMetrics.mockResolvedValue(metrics({}));

    const { result } = renderHook(() => useLiveTrackedMarket(null, null), { wrapper });
    expect(result.current.isResolving).toBe(true);
  });

  it('surfaces a markets fetch failure', async () => {
    mockedMarket.fetchMarkets.mockRejectedValue(new Error('network down'));
    mockedSystem.fetchSystemMetrics.mockResolvedValue(metrics({}));

    const { result } = renderHook(() => useLiveTrackedMarket(null, null), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('network down');
  });
});
