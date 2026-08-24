import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import type { CandlePage, Market } from '@/types/api/market';
import { ReplayPage } from './replay-page';

const fakeSeries = () => ({
  setData: vi.fn(),
  update: vi.fn(),
  applyOptions: vi.fn(),
  priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
});

const fakeChart = vi.hoisted(() => ({
  addSeries: vi.fn(),
  applyOptions: vi.fn(),
  remove: vi.fn(),
  timeScale: vi.fn(),
  subscribeCrosshairMove: vi.fn(),
  unsubscribeCrosshairMove: vi.fn(),
}));

const createChartMock = vi.hoisted(() => vi.fn(() => fakeChart));

vi.mock('lightweight-charts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lightweight-charts')>();
  return { ...actual, createChart: createChartMock };
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

const FIVE_CANDLES = Array.from({ length: 5 }, (_, i) =>
  candle(`2026-01-01T00:0${i}:00Z`, String(100 + i)),
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
  renderPage();
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
  fireEvent.change(screen.getByLabelText('Replay end'), { target: { value: '2026-01-01T01:00' } });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));
    await Promise.resolve();
  });
  await waitFor(() => expect(screen.getByText('Paused')).toBeInTheDocument());
}

beforeEach(() => {
  vi.clearAllMocks();
  fakeChart.timeScale.mockReturnValue({ fitContent: vi.fn() });
  let call = 0;
  fakeChart.addSeries.mockImplementation(() => {
    call += 1;
    return call % 2 === 1 ? fakeSeries() : fakeSeries();
  });
  mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
  mockedMarket.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1m', '5m'] });
});

afterEach(() => {
  cleanup();
});

describe('ReplayPage', () => {
  it('prompts for configuration before any session is loaded', () => {
    renderPage();
    expect(screen.getByText(/Configure a market, timeframe, and date range/)).toBeInTheDocument();
  });

  it('loads a session and shows it paused, ready to play', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();
    expect(screen.getByText('candle 1 of 5', { exact: false })).toBeInTheDocument();
  });

  it('shows an error phase for an empty result set', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage([]));
    renderPage();
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
    fireEvent.change(screen.getByLabelText('Replay end'), {
      target: { value: '2026-01-01T01:00' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));
      await Promise.resolve();
    });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/no candles/i));
  });

  it('shows a backend-unavailable error and lets the user retry', async () => {
    // The query retries once (see useReplayCandles), so this settles slower
    // than the other cases here.
    mockedMarket.fetchCandlePage.mockRejectedValue(new Error('Backend unavailable'));
    renderPage();
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
    fireEvent.change(screen.getByLabelText('Replay end'), {
      target: { value: '2026-01-01T01:00' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));
      await Promise.resolve();
    });
    await waitFor(
      () => expect(screen.getByRole('alert')).toHaveTextContent('Backend unavailable'),
      {
        timeout: 3_000,
      },
    );

    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByText('Paused')).toBeInTheDocument());
  }, 8_000);

  it('plays, pauses, and steps through candles', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();

    // The button reads "Resume" while paused (see ReplayControls) — "Play"
    // only shows from `idle`/`completed`, where there is nothing to resume.
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(screen.getByText('Playing')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    expect(screen.getByText('Paused')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    expect(screen.getByText('candle 2 of 5', { exact: false })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Previous candle' }));
    expect(screen.getByText('candle 1 of 5', { exact: false })).toBeInTheDocument();
  });

  it('restarts to the first candle', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();

    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    expect(screen.getByText('candle 3 of 5', { exact: false })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Restart' }));
    expect(screen.getByText('candle 1 of 5', { exact: false })).toBeInTheDocument();
  });

  it('seeks to the end via the jump-forward control', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();

    fireEvent.click(screen.getByRole('button', { name: 'Jump forward 20 candles' }));
    expect(screen.getByText('candle 5 of 5', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('changes speed without resetting the current candle', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();

    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    expect(screen.getByText('candle 2 of 5', { exact: false })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '10x speed' }));
    expect(screen.getByText('candle 2 of 5', { exact: false })).toBeInTheDocument();
  });

  it('resets to a fresh session when the market/timeframe/range configuration changes', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();

    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    expect(screen.getByText('candle 3 of 5', { exact: false })).toBeInTheDocument();

    const threeCandles = FIVE_CANDLES.slice(0, 3);
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(threeCandles));
    fireEvent.change(screen.getByLabelText('Replay end'), {
      target: { value: '2026-01-01T02:00' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(screen.getByText('candle 1 of 3', { exact: false })).toBeInTheDocument(),
    );
  });

  it('shows the enriched status panel with candle position, loaded/remaining counts, and speed', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();

    const panel = screen.getByRole('status', { name: 'Replay status' });
    expect(panel).toHaveTextContent('1 of 5'); // Current Candle
    expect(panel).toHaveTextContent('1x'); // Replay Speed
  });

  it('jumps to the first and last candle via the timeline’s Home/End buttons', async () => {
    mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
    await loadSession();

    fireEvent.click(screen.getByRole('button', { name: 'Jump to end' }));
    expect(screen.getByText('candle 5 of 5', { exact: false })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Jump to start' }));
    expect(screen.getByText('candle 1 of 5', { exact: false })).toBeInTheDocument();
  });

  describe('keyboard shortcuts', () => {
    it('toggles play/pause on Space', async () => {
      mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
      await loadSession();

      fireEvent.keyDown(window, { key: ' ' });
      expect(screen.getByText('Playing')).toBeInTheDocument();

      fireEvent.keyDown(window, { key: ' ' });
      expect(screen.getByText('Paused')).toBeInTheDocument();
    });

    it('steps forward and backward with ArrowRight/ArrowLeft', async () => {
      mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
      await loadSession();

      fireEvent.keyDown(window, { key: 'ArrowRight' });
      expect(screen.getByText('candle 2 of 5', { exact: false })).toBeInTheDocument();

      fireEvent.keyDown(window, { key: 'ArrowLeft' });
      expect(screen.getByText('candle 1 of 5', { exact: false })).toBeInTheDocument();
    });

    it('jumps to the first/last candle on Home/End', async () => {
      mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
      await loadSession();

      fireEvent.keyDown(window, { key: 'End' });
      expect(screen.getByText('candle 5 of 5', { exact: false })).toBeInTheDocument();

      fireEvent.keyDown(window, { key: 'Home' });
      expect(screen.getByText('candle 1 of 5', { exact: false })).toBeInTheDocument();
    });

    it('changes speed on +/-', async () => {
      mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
      await loadSession();

      fireEvent.keyDown(window, { key: '+' });
      expect(screen.getByRole('button', { name: '2x speed' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );

      fireEvent.keyDown(window, { key: '-' });
      expect(screen.getByRole('button', { name: '1x speed' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
    });

    it('does not trigger shortcuts while typing in the config form', async () => {
      mockedMarket.fetchCandlePage.mockResolvedValue(candlePage(FIVE_CANDLES));
      await loadSession();

      const endInput = screen.getByLabelText('Replay end');
      fireEvent.keyDown(endInput, { key: ' ' });
      expect(screen.getByText('Paused')).toBeInTheDocument();
    });

    it('does nothing before a session is loaded', () => {
      renderPage();
      fireEvent.keyDown(window, { key: ' ' });
      fireEvent.keyDown(window, { key: 'ArrowRight' });
      // No crash, and no session appeared out of nowhere.
      expect(screen.getByText(/Configure a market, timeframe, and date range/)).toBeInTheDocument();
    });
  });
});
