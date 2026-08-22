import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider } from '@mui/material/styles';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import { theme } from '@/theme/theme';
import type { Candle, CandlePage } from '@/types/api/market';
import { ChartContainer } from './chart-container';

vi.mock('@/lib/api/market', () => ({
  fetchCandlePage: vi.fn(),
}));

const fakeSeries = () => ({
  setData: vi.fn(),
  applyOptions: vi.fn(),
  priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
});

const fakeChart = vi.hoisted(() => ({
  addSeries: vi.fn(),
  applyOptions: vi.fn(),
  remove: vi.fn(),
  timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  subscribeCrosshairMove: vi.fn(),
  unsubscribeCrosshairMove: vi.fn(),
}));
const createChartMock = vi.hoisted(() => vi.fn(() => fakeChart));

vi.mock('lightweight-charts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lightweight-charts')>();
  return { ...actual, createChart: createChartMock };
});

const mocked = vi.mocked(marketApi);

function candle(openTime: string, close = '105'): Candle {
  return {
    open_time: openTime,
    close_time: openTime,
    open: '100',
    high: '110',
    low: '90',
    close,
    volume: '10',
    source: 'delta',
  };
}

function candlePage(items: Candle[], total: number): CandlePage {
  return {
    symbol: 'ETHUSD',
    timeframe: '1h',
    items,
    pagination: { total, returned: items.length, has_more: false, limit: 1000, offset: 0 },
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
      total_candles: total,
      first_candle_at: null,
      last_candle_at: null,
      expected_candles: total,
      missing_candles: 0,
      completeness: 100,
    },
    quality: {
      completeness_score: 100,
      freshness_score: 100,
      missing_interval_count: 0,
      missing_intervals: [],
      duplicate_candles: 0,
      out_of_order_candles: 0,
      invalid_ohlc_candles: 0,
      gaps_detected: false,
      overall_quality_score: 100,
    },
    meta: {
      execution_time_ms: 1,
      database_time_ms: 1,
      rows_scanned: items.length,
      rows_returned: items.length,
      cache_status: 'disabled',
      generated_at: '2026-08-01T00:00:00Z',
    },
  };
}

function renderContainer(props: Partial<ComponentProps<typeof ChartContainer>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <ChartContainer symbol="ETHUSD" timeframe="1h" {...props} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

let candleSeries: ReturnType<typeof fakeSeries>;
let volumeSeries: ReturnType<typeof fakeSeries>;

beforeEach(() => {
  vi.clearAllMocks();
  candleSeries = fakeSeries();
  volumeSeries = fakeSeries();
  let call = 0;
  fakeChart.addSeries.mockImplementation(() => {
    call += 1;
    return call === 1 ? candleSeries : volumeSeries;
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ChartContainer', () => {
  it('prompts for a market and timeframe when neither is selected', () => {
    renderContainer({ symbol: null, timeframe: null });
    expect(
      screen.getByText('Select a market and timeframe to view the candlestick chart.'),
    ).toBeInTheDocument();
    expect(mocked.fetchCandlePage).not.toHaveBeenCalled();
  });

  it('shows a loading state while the first page is in flight', () => {
    mocked.fetchCandlePage.mockReturnValue(new Promise(() => undefined));
    renderContainer();
    expect(screen.getByRole('status', { name: 'Loading chart' })).toBeInTheDocument();
  });

  it('shows an error with a retry action on API failure', async () => {
    mocked.fetchCandlePage.mockRejectedValue(new Error('boom'));
    renderContainer();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load chart data');
    expect(alert).toHaveTextContent('boom');
  });

  it('shows an empty state when no candles are returned', async () => {
    mocked.fetchCandlePage.mockResolvedValue(candlePage([], 0));
    renderContainer();
    expect(await screen.findByRole('status', { name: 'No chart data' })).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it('renders the chart, toolbar, and legend once candles load', async () => {
    mocked.fetchCandlePage.mockResolvedValue(
      candlePage([candle('2026-08-01T00:00:00Z'), candle('2026-08-01T01:00:00Z', '108')], 2),
    );
    renderContainer();

    await waitFor(() => expect(createChartMock).toHaveBeenCalledTimes(1));
    expect(screen.getByText('ETHUSD · 1h')).toBeInTheDocument();
    expect(screen.getByText('2 candles')).toBeInTheDocument();
    expect(candleSeries.setData).toHaveBeenCalled();
    // No hover yet: legend falls back to the latest candle.
    expect(screen.getByLabelText('Candle details at crosshair')).toHaveTextContent('108.00');
  });

  it('refetches with new parameters when the symbol or timeframe changes', async () => {
    mocked.fetchCandlePage.mockResolvedValue(candlePage([candle('2026-08-01T00:00:00Z')], 1));
    const { rerender } = renderContainer({ symbol: 'ETHUSD', timeframe: '1h' });
    await waitFor(() => expect(mocked.fetchCandlePage).toHaveBeenCalledTimes(1));

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <ThemeProvider theme={theme}>
        <QueryClientProvider client={client}>
          <ChartContainer symbol="BTCUSD" timeframe="4h" />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    await waitFor(() =>
      expect(mocked.fetchCandlePage).toHaveBeenCalledWith(
        'BTCUSD',
        '4h',
        expect.objectContaining({ dir: 'desc' }),
      ),
    );
  });
});
