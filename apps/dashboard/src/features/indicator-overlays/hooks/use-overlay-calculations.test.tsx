import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as indicatorApi from '@/lib/api/indicators';
import type { OverlayConfig } from '../store/use-overlay-store';
import { useOverlayCalculations } from './use-overlay-calculations';

vi.mock('@/lib/api/indicators', () => ({
  calculateIndicatorBatch: vi.fn(),
}));

const mocked = vi.mocked(indicatorApi);

function overlay(overrides: Partial<OverlayConfig> = {}): OverlayConfig {
  return {
    id: 'overlay-1',
    indicator: 'sma',
    label: 'SMA(20)',
    params: { period: '20' },
    enabled: true,
    colorIndex: 0,
    ...overrides,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.calculateIndicatorBatch.mockResolvedValue({
    symbol: 'ETHUSD',
    timeframe: '1h',
    timestamps: [],
    results: [],
    candles_analyzed: 0,
    database_time_ms: 0,
    engine_version: '1.0.0',
    generated_at: '2026-01-01T00:00:00Z',
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useOverlayCalculations', () => {
  it('does not call the API when there are no enabled overlays', () => {
    renderHook(() => useOverlayCalculations({ symbol: 'ETHUSD', timeframe: '1h', overlays: [] }), {
      wrapper,
    });
    expect(mocked.calculateIndicatorBatch).not.toHaveBeenCalled();
  });

  it('does not call the API without a symbol or timeframe', () => {
    renderHook(
      () => useOverlayCalculations({ symbol: null, timeframe: '1h', overlays: [overlay()] }),
      { wrapper },
    );
    expect(mocked.calculateIndicatorBatch).not.toHaveBeenCalled();
  });

  it('sends only the enabled overlays as batch requests', async () => {
    const overlays = [overlay({ id: 'a' }), overlay({ id: 'b', enabled: false, indicator: 'ema' })];
    renderHook(() => useOverlayCalculations({ symbol: 'ETHUSD', timeframe: '1h', overlays }), {
      wrapper,
    });
    await waitFor(() => expect(mocked.calculateIndicatorBatch).toHaveBeenCalledTimes(1));
    const [, body] = mocked.calculateIndicatorBatch.mock.calls[0]!;
    expect(body.requests).toEqual([{ indicator: 'sma', params: { period: '20' } }]);
  });

  it('builds an identical request regardless of the enabled overlays’ list order', async () => {
    const a = overlay({ id: 'a', indicator: 'sma' });
    const b = overlay({ id: 'b', indicator: 'ema', colorIndex: 1 });

    renderHook(
      () => useOverlayCalculations({ symbol: 'ETHUSD', timeframe: '1h', overlays: [a, b] }),
      { wrapper },
    );
    await waitFor(() => expect(mocked.calculateIndicatorBatch).toHaveBeenCalledTimes(1));
    const firstOrder = mocked.calculateIndicatorBatch.mock.calls[0]![1]!.requests;

    mocked.calculateIndicatorBatch.mockClear();
    renderHook(
      () => useOverlayCalculations({ symbol: 'ETHUSD', timeframe: '1h', overlays: [b, a] }),
      { wrapper },
    );
    await waitFor(() => expect(mocked.calculateIndicatorBatch).toHaveBeenCalledTimes(1));
    const secondOrder = mocked.calculateIndicatorBatch.mock.calls[0]![1]!.requests;

    expect(firstOrder).toEqual(secondOrder);
  });
});
