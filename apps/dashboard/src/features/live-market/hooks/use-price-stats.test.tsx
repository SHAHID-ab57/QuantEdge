import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import { total24hVolume, usePriceStats } from './use-price-stats';

vi.mock('@/lib/api/market', () => ({
  fetchCandleStats: vi.fn(),
}));

const mocked = vi.mocked(marketApi);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('total24hVolume', () => {
  it('derives total volume from the average and candle count', () => {
    expect(total24hVolume('10.5', 4)).toBeCloseTo(42);
  });

  it('returns null when there are no candles', () => {
    expect(total24hVolume('10.5', 0)).toBeNull();
  });

  it('returns null when the average is null', () => {
    expect(total24hVolume(null, 10)).toBeNull();
  });
});

describe('usePriceStats', () => {
  it('is disabled until a symbol is selected', () => {
    const { result } = renderHook(() => usePriceStats(null), { wrapper });
    expect(result.current.isPending).toBe(true);
    expect(mocked.fetchCandleStats).not.toHaveBeenCalled();
  });

  it('queries a fixed 5m granularity over roughly the last 24 hours', async () => {
    mocked.fetchCandleStats.mockResolvedValue({
      symbol: 'ETHUSD',
      timeframe: '5m',
      start: null,
      end: null,
      total_candles: 288,
      highest_price: '2000',
      lowest_price: '1900',
      average_volume: '10',
      first_candle: null,
      last_candle: null,
    });

    const { result } = renderHook(() => usePriceStats('ETHUSD'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mocked.fetchCandleStats).toHaveBeenCalledWith(
      'ETHUSD',
      '5m',
      expect.objectContaining({
        start: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/),
        end: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/),
      }),
    );
    const args = mocked.fetchCandleStats.mock.calls[0]!;
    const params = args[2] as { start: string; end: string };
    const spanMs = Date.parse(params.end) - Date.parse(params.start);
    expect(spanMs).toBeCloseTo(86_400_000, -3);
  });
});
