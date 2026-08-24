import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { Indicator, IndicatorCalculation } from '@/types/api/indicators';
import { IndicatorMetadataCard } from './indicator-metadata-card';

afterEach(() => {
  cleanup();
});

function sma(overrides: Partial<Indicator> = {}): Indicator {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'Stub.',
    category: 'trend',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period parameter.',
    parameters: [],
    outputs: [{ name: 'sma', label: 'SMA', description: '' }],
    ...overrides,
  };
}

function calculation(overrides: Partial<IndicatorCalculation> = {}): IndicatorCalculation {
  return {
    symbol: 'ETHUSD',
    timeframe: '1h',
    indicator: sma(),
    parameters: { period: 20 },
    timestamps: [],
    series: [],
    meta: {
      candles_analyzed: 50,
      warmup_candles: 20,
      execution_time_ms: 0.1,
      database_time_ms: 1,
      cache_status: 'hit',
      generated_at: '2026-01-01T00:00:00Z',
    },
    ...overrides,
  };
}

function renderCard(indicator: Indicator, result?: IndicatorCalculation) {
  return render(
    <ThemeProvider theme={theme}>
      <IndicatorMetadataCard indicator={indicator} result={result} />
    </ThemeProvider>,
  );
}

describe('IndicatorMetadataCard', () => {
  it('shows the category', () => {
    renderCard(sma());
    expect(screen.getByText('trend')).toBeInTheDocument();
  });

  it('describes a single-series indicator', () => {
    renderCard(sma());
    expect(screen.getByText('Single series (SMA)')).toBeInTheDocument();
  });

  it('describes a multi-series indicator by counting its outputs', () => {
    renderCard(
      sma({
        outputs: [
          { name: 'upper', label: 'Upper', description: '' },
          { name: 'lower', label: 'Lower', description: '' },
        ],
      }),
    );
    expect(screen.getByText('2 series (Upper, Lower)')).toBeInTheDocument();
  });

  it('shows the indicator-published warmup description before any calculation has run', () => {
    renderCard(sma());
    expect(screen.getByText('Equal to the period parameter.')).toBeInTheDocument();
  });

  it('shows the actual warmup candle count once a calculation exists', () => {
    renderCard(sma(), calculation());
    expect(screen.getByText('20 candles')).toBeInTheDocument();
  });

  it('shows the live cache status once a calculation exists', () => {
    renderCard(sma(), calculation({ meta: { ...calculation().meta, cache_status: 'hit' } }));
    expect(screen.getByText('hit')).toBeInTheDocument();
  });

  it('shows a dash for cache status before any calculation has run', () => {
    renderCard(sma());
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('shows the indicator-published version and author, sourced from the backend', () => {
    renderCard(sma());
    expect(screen.getByText('1.0.0')).toBeInTheDocument();
    expect(screen.getByText('Eth AI Platform')).toBeInTheDocument();
  });

  it('shows the indicator-published time complexity rather than a hardcoded string', () => {
    renderCard(sma({ complexity: 'O(n log n) — a hypothetical future indicator.' }));
    expect(screen.getByText('O(n log n) — a hypothetical future indicator.')).toBeInTheDocument();
  });

  it('derives supported price sources from the source parameter, not a hardcoded list', () => {
    renderCard(
      sma({
        parameters: [
          {
            name: 'source',
            type: 'string',
            label: 'Source',
            description: '',
            default: 'close',
            required: false,
            minimum: null,
            maximum: null,
            choices: ['open', 'high', 'low', 'close'],
          },
        ],
      }),
    );
    expect(screen.getByText('open, high, low, close')).toBeInTheDocument();
  });

  it('claims replay/backtesting/feature-engineering support as an architectural fact', () => {
    renderCard(sma());
    expect(
      screen.getByText('Supports Replay / Backtesting / AI Feature Engineering'),
    ).toBeInTheDocument();
  });
});
