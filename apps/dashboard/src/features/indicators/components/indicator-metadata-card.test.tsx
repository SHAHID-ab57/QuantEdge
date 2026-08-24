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

  it('shows a placeholder warmup requirement before any calculation has run', () => {
    renderCard(sma());
    expect(screen.getByText('Depends on parameters')).toBeInTheDocument();
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

  it('states plainly that no engine version is exposed, rather than fabricating one', () => {
    renderCard(sma());
    expect(screen.getByText('Not exposed by the API')).toBeInTheDocument();
  });

  it('claims replay/backtesting/feature-engineering support as an architectural fact', () => {
    renderCard(sma());
    expect(
      screen.getByText('Supports Replay / Backtesting / AI Feature Engineering'),
    ).toBeInTheDocument();
  });
});
