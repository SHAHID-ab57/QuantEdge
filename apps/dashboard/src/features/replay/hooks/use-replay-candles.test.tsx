import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Candle } from '@/types/api/market';
import {
  MAX_REPLAY_CANDLES,
  REPLAY_PAGE_LIMIT,
  replayConfigKey,
  useReplayCandles,
} from './use-replay-candles';

vi.mock('@/lib/api/paginate-candles', () => ({ fetchAllCandles: vi.fn() }));

const { fetchAllCandles } = await import('@/lib/api/paginate-candles');
const mockedFetchAllCandles = vi.mocked(fetchAllCandles);

function candle(openTime: string): Candle {
  return {
    open_time: openTime,
    close_time: openTime,
    open: '1',
    high: '1',
    low: '1',
    close: '1',
    volume: '1',
    source: 'test',
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const config = {
  symbol: 'ETHUSD',
  timeframe: '1m',
  start: '2026-01-01T00:00:00Z',
  end: '2026-01-01T01:00:00Z',
};

describe('replayConfigKey', () => {
  it('produces a distinct key per field, so a change to any one triggers a refetch', () => {
    const base = replayConfigKey(config);
    expect(replayConfigKey({ ...config, symbol: 'BTCUSD' })).not.toBe(base);
    expect(replayConfigKey({ ...config, timeframe: '5m' })).not.toBe(base);
    expect(replayConfigKey({ ...config, start: '2026-01-02T00:00:00Z' })).not.toBe(base);
    expect(replayConfigKey({ ...config, end: '2026-01-02T00:00:00Z' })).not.toBe(base);
  });

  it('is stable for identical config values', () => {
    expect(replayConfigKey(config)).toBe(replayConfigKey({ ...config }));
  });
});

describe('useReplayCandles', () => {
  it('does not fetch when config is null', () => {
    const { result } = renderHook(() => useReplayCandles(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(mockedFetchAllCandles).not.toHaveBeenCalled();
  });

  it('loads the whole session at once, sorted ascending, at the shared page limit', async () => {
    mockedFetchAllCandles.mockResolvedValueOnce({
      candles: [candle('2026-01-01T00:00:00Z')],
      firstPage: {} as never,
      truncated: false,
    });
    const { result } = renderHook(() => useReplayCandles(config), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.candles).toHaveLength(1);
    expect(mockedFetchAllCandles).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: 'ETHUSD',
        timeframe: '1m',
        limit: REPLAY_PAGE_LIMIT,
        sort: 'open_time',
        dir: 'asc',
      }),
      undefined,
      Math.ceil(MAX_REPLAY_CANDLES / REPLAY_PAGE_LIMIT),
    );
  });

  it('reports truncated when the underlying fetch hit its page cap', async () => {
    mockedFetchAllCandles.mockResolvedValueOnce({
      candles: [candle('2026-01-01T00:00:00Z')],
      firstPage: {} as never,
      truncated: true,
    });
    const { result } = renderHook(() => useReplayCandles(config), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.truncated).toBe(true);
  });

  it('surfaces a network failure as an error result', async () => {
    // The hook retries once (a real network blip is common enough to be
    // worth one automatic retry), so this settles slower than the other
    // cases here — hence the longer `waitFor` timeout.
    mockedFetchAllCandles.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useReplayCandles(config), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 3_000 });
    expect(result.current.error?.message).toBe('network down');
  }, 5_000);
});
