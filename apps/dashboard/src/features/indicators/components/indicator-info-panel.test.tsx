import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { Indicator } from '@/types/api/indicators';
import { IndicatorInfoPanel } from './indicator-info-panel';

afterEach(() => {
  cleanup();
});

function rsi(overrides: Partial<Indicator> = {}): Indicator {
  return {
    name: 'rsi',
    label: 'Relative Strength Index',
    description: 'A 0-100 momentum oscillator.',
    category: 'momentum',
    parameters: [],
    outputs: [],
    ...overrides,
  };
}

function renderPanel(indicator: Indicator, defaultExpanded?: boolean) {
  return render(
    <ThemeProvider theme={theme}>
      <IndicatorInfoPanel indicator={indicator} defaultExpanded={defaultExpanded} />
    </ThemeProvider>,
  );
}

describe('IndicatorInfoPanel', () => {
  it('shows the indicator name and category', () => {
    renderPanel(rsi());
    expect(screen.getByText('Relative Strength Index')).toBeInTheDocument();
    expect(screen.getByText('momentum')).toBeInTheDocument();
  });

  it('is expanded by default', () => {
    renderPanel(rsi());
    expect(screen.getByText(/momentum oscillator comparing/)).toBeVisible();
  });

  it('collapses when its header is clicked', () => {
    renderPanel(rsi());
    fireEvent.click(screen.getByText('Relative Strength Index'));
    expect(screen.getByRole('button', { expanded: false })).toBeInTheDocument();
  });

  it('respects an explicit defaultExpanded=false', () => {
    renderPanel(rsi(), false);
    expect(screen.getByRole('button', { expanded: false })).toBeInTheDocument();
  });

  it('renders the formula for a curated indicator', () => {
    renderPanel(rsi());
    expect(screen.getByText(/RS = average gain/)).toBeInTheDocument();
  });

  it('lists advantages and limitations', () => {
    renderPanel(rsi());
    expect(screen.getByText('Advantages')).toBeInTheDocument();
    expect(screen.getByText('Limitations')).toBeInTheDocument();
    expect(screen.getByText(/Fixed 0-100 scale/)).toBeInTheDocument();
  });

  it('lists recommended values per parameter', () => {
    renderPanel(rsi());
    expect(screen.getByText(/period:/)).toBeInTheDocument();
    expect(screen.getByText(/7, 9, 14, 21, 25/)).toBeInTheDocument();
  });

  it('shows the methodology reference when curated', () => {
    renderPanel(rsi());
    expect(screen.getByText(/Wilder Jr\./)).toBeInTheDocument();
  });

  it('degrades gracefully for an indicator with no curated content', () => {
    const uncurated = rsi({ name: 'macd', label: 'MACD', description: 'Stub description.' });
    renderPanel(uncurated);
    expect(screen.getByText('Stub description.')).toBeInTheDocument();
    // Formula, recommended parameters, advantages, and limitations all
    // degrade to the same honest placeholder rather than fabricated content.
    expect(
      screen.getAllByText('Not yet documented for this indicator.').length,
    ).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText(/Wilder/)).not.toBeInTheDocument();
  });
});
