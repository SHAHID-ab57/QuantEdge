import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import type { CandlePage, Market } from '@/types/api/market';
import { ReplayPage } from './replay-page';

/**
 * A render-cost regression guard, in the same spirit as the Live Trade
 * Analytics dashboard's `trade-tape.render.test.tsx`: rather than inferring
 * "did this component re-render" indirectly, spy on a hook it calls
 * unconditionally during its own render body. If `React.memo` correctly
 * bails out because `ReplayConfigForm`'s props are unchanged, React does
 * not invoke the component function at all — so it does not call
 * `useTimeframes()` again either. Counting those calls turns "did the
 * memo actually prevent wasted render work" into an exact number instead
 * of an inference from DOM output, which could look identical whether or
 * not the component actually re-ran.
 *
 * This is a real regression this review found: before this pass,
 * `ReplayConfigForm` had no `React.memo` wrapper at all, so every
 * playback tick (`ReplayPage` re-rendering because `currentIndex`
 * changed) re-ran the entire config form — a fresh `useForm`/`useMarkets`/
 * `useTimeframes` render cycle for a component whose own props never
 * changed during playback.
 */
vi.mock('@/features/history/hooks/use-history-data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/history/hooks/use-history-data')>();
  return { ...actual, useTimeframes: vi.fn(actual.useTimeframes) };
});

const { useTimeframes } = await import('@/features/history/hooks/use-history-data');
const useTimeframesSpy = vi.mocked(useTimeframes);

vi.mock('lightweight-charts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lightweight-charts')>();
  const fakeSeries = () => ({
    setData: vi.fn(),
    update: vi.fn(),
    applyOptions: vi.fn(),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
  });
  const fakeChart = {
    addSeries: vi.fn(() => fakeSeries()),
    applyOptions: vi.fn(),
    remove: vi.fn(),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
  };
  return { ...actual, createChart: vi.fn(() => fakeChart) };
});

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchCandlePage: vi.fn(),
}));

const mockedMarket = vi.mocked(marketApi);

const markets: Market[] = [
  {
    id: '1',
    symbol: 'ETHUSD',
    exchange: 'Delta Exchange',
    exchange_id: 'e1',
    base_asset: 'ETH',
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 1,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.01',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: null,
  },
];

function candle(openTimeIso: string, close: string) {
  return {
    open_time: openTimeIso,
    close_time: openTimeIso,
    open: close,
    high: close,
    low: close,
    close,
    volume: '10',
    source: 'delta_rest',
  };
}

function candlePage(items: ReturnType<typeof candle>[]): CandlePage {
  return {
    items,
    pagination: {
      total: items.length,
      returned: items.length,
      has_more: false,
      limit: 1000,
      offset: 0,
    },
    statistics: {
      total_candles: items.length,
      expected_candles: items.length,
      missing_candles: 0,
      completeness: 100,
    },
    quality: {
      freshness_score: 100,
      overall_quality_score: 100,
      duplicate_candles: 0,
      out_of_order_candles: 0,
      invalid_ohlc_candles: 0,
    },
  } as unknown as CandlePage;
}

const CANDLES = Array.from({ length: 20 }, (_, i) =>
  candle(new Date(Date.parse('2026-01-01T00:00:00Z') + i * 60_000).toISOString(), String(100 + i)),
);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReplayPage />
    </QueryClientProvider>,
  );
}

async function loadSession() {
  const combobox = screen.getByRole('combobox', { name: 'Select a market to replay' });
  fireEvent.mouseDown(combobox);
  fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
  await waitFor(() =>
    expect(screen.getByRole('combobox', { name: 'Timeframe' })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    ),
  );
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Timeframe' }));
  fireEvent.click(await screen.findByRole('option', { name: '1m' }));
  fireEvent.change(screen.getByLabelText('Replay start'), {
    target: { value: '2026-01-01T00:00' },
  });
  fireEvent.change(screen.getByLabelText('Replay end'), { target: { value: '2026-01-01T00:20' } });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));
    await Promise.resolve();
  });
  await waitFor(() => expect(screen.getByText('Paused')).toBeInTheDocument());
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
  mockedMarket.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1m'] });
  mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(CANDLES));
});

afterEach(() => {
  cleanup();
});

describe('ReplayPage render cost', () => {
  // A generous per-test timeout: these fill out and submit the full config
  // form (react-hook-form + Zod + TanStack Query all in the mix) before
  // measuring anything, which can run well past the 5s default under the
  // CPU contention of the full test suite, even though each test is fast
  // in isolation.
  it('does not re-render ReplayConfigForm while stepping through candles', async () => {
    renderPage();
    await loadSession();

    const callsAfterLoad = useTimeframesSpy.mock.calls.length;
    expect(callsAfterLoad).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));

    // Three ticks — `ReplayPage` re-rendered three times, and the chart,
    // timeline, and status panel all legitimately updated — but the
    // config form's own render body, and therefore its `useTimeframes()`
    // call, must not have run again.
    expect(useTimeframesSpy.mock.calls.length).toBe(callsAfterLoad);
  }, 15_000);

  it('does not re-render ReplayConfigForm during auto-play either', async () => {
    renderPage();
    await loadSession();
    const callsAfterLoad = useTimeframesSpy.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next candle' })); // a manual step layered on top

    expect(useTimeframesSpy.mock.calls.length).toBe(callsAfterLoad);
  }, 15_000);

  it('does re-render ReplayConfigForm when its own props genuinely change (loading state)', async () => {
    renderPage();
    await loadSession();
    const callsAfterLoad = useTimeframesSpy.mock.calls.length;

    // Switching configuration flips the form's own `disabled` prop
    // (`engine.phase === 'loading'`) — a real prop change, which
    // *should* cause a re-render, proving the memo isn't over-
    // suppressing updates the form genuinely needs.
    fireEvent.change(screen.getByLabelText('Replay end'), {
      target: { value: '2026-01-01T00:15' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));

    await waitFor(() => expect(useTimeframesSpy.mock.calls.length).toBeGreaterThan(callsAfterLoad));
  }, 15_000);
});
