import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as indicatorApi from '@/lib/api/indicators';
import * as marketApi from '@/lib/api/market';
import { theme } from '@/theme/theme';
import type { IndicatorCalculation, IndicatorCatalog } from '@/types/api/indicators';
import type { Market } from '@/types/api/market';
import { IndicatorsPage } from './indicators-page';

vi.mock('@/lib/api/indicators', () => ({
  fetchIndicators: vi.fn(),
  fetchIndicator: vi.fn(),
  calculateIndicator: vi.fn(),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
  fetchLatestCandle: vi.fn(),
}));

const mockedIndicators = vi.mocked(indicatorApi);
const mockedMarket = vi.mocked(marketApi);

const markets: Market[] = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    exchange: 'Delta Exchange',
    exchange_id: '22222222-2222-4222-8222-222222222222',
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

const catalog: IndicatorCatalog = {
  total: 2,
  categories: ['momentum', 'trend'],
  indicators: [
    {
      name: 'sma',
      label: 'Simple Moving Average',
      description: 'The unweighted mean of the last N values.',
      category: 'trend',
      version: '1.0.0',
      author: 'Eth AI Platform',
      complexity: 'O(n)',
      warmup_description: 'Equal to the period parameter.',
      parameters: [
        {
          name: 'period',
          type: 'int',
          label: 'Period',
          description: 'Number of candles averaged.',
          default: 20,
          required: false,
          minimum: 1,
          maximum: 1000,
          choices: [],
        },
        {
          name: 'source',
          type: 'string',
          label: 'Source',
          description: 'Which price to average.',
          default: 'close',
          required: false,
          minimum: null,
          maximum: null,
          choices: ['open', 'high', 'low', 'close'],
        },
      ],
      outputs: [{ name: 'sma', label: 'SMA', description: 'The moving average.' }],
    },
    {
      name: 'rsi',
      label: 'Relative Strength Index',
      description: 'A 0-100 momentum oscillator.',
      category: 'momentum',
      version: '1.0.0',
      author: 'Eth AI Platform',
      complexity: 'O(n)',
      warmup_description: 'Equal to the period parameter.',
      parameters: [
        {
          name: 'period',
          type: 'int',
          label: 'Period',
          description: 'Look-back window.',
          default: 14,
          required: false,
          minimum: 2,
          maximum: 1000,
          choices: [],
        },
      ],
      outputs: [{ name: 'rsi', label: 'RSI', description: 'The oscillator.' }],
    },
  ],
};

const calculation: IndicatorCalculation = {
  symbol: 'ETHUSD',
  timeframe: '1h',
  indicator: catalog.indicators[0]!,
  parameters: { period: 20, source: 'close' },
  timestamps: ['2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z'],
  series: [{ name: 'sma', label: 'SMA(20)', values: [null, 3055.25] }],
  meta: {
    candles_analyzed: 2,
    warmup_candles: 1,
    execution_time_ms: 0.08,
    database_time_ms: 3.2,
    cache_status: 'miss',
    generated_at: '2026-01-01T02:00:00Z',
  },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <IndicatorsPage />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

/** Fill market → timeframe → indicator, the prerequisites for Calculate. */
async function configure(indicatorLabel = 'Simple Moving Average') {
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Select a market for the chart' }));
  fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));

  await waitFor(() =>
    expect(screen.getByRole('combobox', { name: 'Timeframe' })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    ),
  );
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Timeframe' }));
  fireEvent.click(await screen.findByRole('option', { name: '1h' }));

  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Select an indicator' }));
  fireEvent.click(await screen.findByRole('option', { name: new RegExp(indicatorLabel) }));
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
  mockedMarket.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1h', '1d'] });
  mockedMarket.fetchLatestCandle.mockResolvedValue({
    symbol: 'ETHUSD',
    timeframe: '1h',
    candle: {
      open_time: '2026-01-01T01:00:00Z',
      close_time: '2026-01-01T02:00:00Z',
      open: '3050',
      high: '3060',
      low: '3040',
      close: '3100',
      volume: '100',
      source: 'delta',
    },
  });
  mockedIndicators.fetchIndicators.mockResolvedValue(catalog);
  mockedIndicators.calculateIndicator.mockResolvedValue(calculation);
});

afterEach(() => {
  cleanup();
});

describe('IndicatorsPage — loading and error states', () => {
  it('shows a loading state while the catalogue loads', () => {
    mockedIndicators.fetchIndicators.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading indicators' })).toBeInTheDocument();
  });

  it('shows an error with a retry action when the catalogue fails', async () => {
    mockedIndicators.fetchIndicators.mockRejectedValue(new Error('backend unavailable'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('backend unavailable');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('retries the catalogue when Retry is pressed', async () => {
    mockedIndicators.fetchIndicators.mockRejectedValueOnce(new Error('backend unavailable'));
    renderPage();
    await screen.findByRole('alert');

    mockedIndicators.fetchIndicators.mockResolvedValue(catalog);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('prompts for configuration before anything has been calculated', async () => {
    renderPage();
    expect(
      await screen.findByText(/Choose a market, timeframe, and indicator above/),
    ).toBeInTheDocument();
  });
});

describe('IndicatorsPage — configuration', () => {
  it('lists every indicator from the catalogue', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Select an indicator' }));
    expect(
      await screen.findByRole('option', { name: /Simple Moving Average/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Relative Strength Index/ })).toBeInTheDocument();
  });

  it('builds the parameter form from the selected indicator specs', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    expect(screen.getByLabelText('Period')).toHaveValue(20);
    expect(screen.getByRole('combobox', { name: 'Source' })).toBeInTheDocument();
  });

  it('reseeds the form when a different indicator is chosen', async () => {
    // SMA defaults period to 20, RSI to 14 — carrying 20 over would
    // silently calculate something the researcher did not ask for.
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();
    expect(screen.getByLabelText('Period')).toHaveValue(20);

    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Select an indicator' }));
    fireEvent.click(await screen.findByRole('option', { name: /Relative Strength Index/ }));
    await waitFor(() => expect(screen.getByLabelText('Period')).toHaveValue(14));
  });

  it('explains that no indicator is selected yet', async () => {
    renderPage();
    expect(
      await screen.findByText('Select an indicator to configure its parameters.'),
    ).toBeInTheDocument();
  });

  it('disables Calculate until a market, timeframe, and indicator are chosen', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    expect(screen.getByRole('button', { name: 'Calculate' })).toBeDisabled();
  });
});

describe('IndicatorsPage — calculation', () => {
  it('calculates and renders the resulting series', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    const summary = await screen.findByRole('status', { name: 'Indicator summary' });
    expect(within(summary).getByText('SMA(20)')).toBeInTheDocument();
    expect(within(summary).getByText('3,055.25')).toBeInTheDocument();
  });

  it('shows current price and distance once the latest candle resolves', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    await screen.findByRole('status', { name: 'Indicator summary' });

    expect(await screen.findByText(/Current Price: 3,100/)).toBeInTheDocument();
    // 3055.25 - 3100 = -44.75
    expect(screen.getByText(/Distance: -44\.75/)).toBeInTheDocument();
  });

  it('sends the configured market, timeframe, and parameters', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    await waitFor(() =>
      expect(mockedIndicators.calculateIndicator).toHaveBeenCalledWith('ETHUSD', 'sma', {
        timeframe: '1h',
        params: { period: '5', source: 'close' },
        limit: undefined,
      }),
    );
  });

  it('does not calculate on every keystroke — only on submit', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '50' } });
    expect(mockedIndicators.calculateIndicator).not.toHaveBeenCalled();
  });

  it('blocks an out-of-range parameter client-side without calling the backend', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    expect(await screen.findByText('Must be at least 1')).toBeInTheDocument();
    expect(mockedIndicators.calculateIndicator).not.toHaveBeenCalled();
  });

  it('surfaces a backend calculation error with a retry action', async () => {
    mockedIndicators.calculateIndicator.mockRejectedValue(
      new Error("Indicator 'sma' needs at least 20 candles"),
    );
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('needs at least 20 candles');
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows a loading state while the calculation is in flight', async () => {
    mockedIndicators.calculateIndicator.mockReturnValue(new Promise(() => undefined));
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    expect(
      await screen.findByRole('status', { name: 'Calculating indicator' }),
    ).toBeInTheDocument();
  });
});

describe('IndicatorsPage — indicator information panel', () => {
  it('shows research content for the selected indicator once configured', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();

    expect(screen.getByText(/Smooths price by averaging/)).toBeInTheDocument();
  });

  it('shows nothing before an indicator is selected', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    expect(screen.queryByText(/Smooths price by averaging/)).not.toBeInTheDocument();
  });

  it('degrades gracefully for an indicator with no curated research content', async () => {
    // The engine is designed to grow toward hundreds of indicators; the
    // knowledge base can only ever curate a fraction of them, so a
    // catalogue entry it has never seen must still render something
    // honest here, sourced from the catalogue's own description.
    mockedIndicators.fetchIndicators.mockResolvedValue({
      ...catalog,
      total: 3,
      indicators: [
        ...catalog.indicators,
        {
          name: 'macd',
          label: 'MACD',
          description: 'Moving Average Convergence Divergence.',
          category: 'trend',
          version: '1.0.0',
          author: 'Eth AI Platform',
          complexity: 'O(n)',
          warmup_description: 'Equal to the period parameter.',
          parameters: [],
          outputs: [{ name: 'macd', label: 'MACD', description: '' }],
        },
      ],
    });
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Select an indicator' }));
    fireEvent.click(await screen.findByRole('option', { name: /MACD/ }));

    expect(screen.getByText('Moving Average Convergence Divergence.')).toBeInTheDocument();
    expect(screen.getAllByText('Not yet documented for this indicator.').length).toBeGreaterThan(0);
  });
});

describe('IndicatorsPage — metadata card', () => {
  it('shows the selected indicator category once configured', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();
    expect(screen.getByText('Indicator Metadata')).toBeInTheDocument();
  });

  it('shows the live cache status once a calculation has run', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    await screen.findByRole('status', { name: 'Indicator summary' });
    // "miss" also appears in the results panel's own Cache stat tile —
    // the metadata card must report the same live status independently.
    expect(screen.getAllByText('miss').length).toBeGreaterThanOrEqual(2);
  });
});

describe('IndicatorsPage — export', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock');
    URL.revokeObjectURL = vi.fn();
  });

  it('offers export actions once a calculation has run', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    await screen.findByRole('status', { name: 'Indicator summary' });

    fireEvent.click(screen.getByRole('button', { name: 'Export' }));
    expect(screen.getByRole('menuitem', { name: 'Export CSV' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Copy API Request' })).toBeInTheDocument();
  });

  it('offers no export action before a calculation exists', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();
    expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  });
});

describe('IndicatorsPage — recent calculations', () => {
  it('records a successful calculation for later rerun', async () => {
    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    await screen.findByRole('status', { name: 'Indicator summary' });

    expect(await screen.findByText('Simple Moving Average · ETHUSD · 1h')).toBeInTheDocument();
  });

  it('reruns a recorded calculation with one click, updating the results to match', async () => {
    // Two distinct configurations produce two distinguishable results;
    // rerunning the older one must bring its result back, proving the
    // click actually re-drives the calculation rather than just
    // highlighting the list entry.
    mockedIndicators.calculateIndicator.mockImplementation((_symbol, _indicator, options) => {
      const period = options.params?.period ?? '20';
      return Promise.resolve({
        ...calculation,
        parameters: { period: Number(period), source: 'close' },
        series: [
          {
            name: 'sma',
            label: `SMA(${period})`,
            values: [null, period === '50' ? 999 : 3055.25],
          },
        ],
      });
    });

    renderPage();
    await screen.findByRole('combobox', { name: 'Select an indicator' });
    await configure();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    await screen.findByRole('status', { name: 'Indicator summary' });
    expect(
      within(screen.getByRole('status', { name: 'Indicator summary' })).getByText('3,055.25'),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    await waitFor(() =>
      expect(
        within(screen.getByRole('status', { name: 'Indicator summary' })).getByText('999'),
      ).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByText(/period=20, source=close/));

    await waitFor(() =>
      expect(
        within(screen.getByRole('status', { name: 'Indicator summary' })).getByText('3,055.25'),
      ).toBeInTheDocument(),
    );
  });

  it('explains that the list is empty before anything has been calculated', async () => {
    renderPage();
    expect(await screen.findByText(/will appear here/)).toBeInTheDocument();
  });
});
