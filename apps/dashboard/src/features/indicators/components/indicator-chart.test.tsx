import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { IndicatorSeries } from '@/types/api/indicators';
import type { ChartConfig } from '../lib/indicator-knowledge';
import { IndicatorChart } from './indicator-chart';

afterEach(() => {
  cleanup();
});

function renderChart(series: IndicatorSeries[], config: ChartConfig, height?: number) {
  return render(
    <ThemeProvider theme={theme}>
      <IndicatorChart series={series} config={config} height={height} />
    </ThemeProvider>,
  );
}

const line: ChartConfig = { kind: 'line' };

describe('IndicatorChart', () => {
  it('renders an accessible svg naming every series', () => {
    renderChart([{ name: 'sma', label: 'SMA(20)', values: [1, 2, 3] }], line);
    expect(screen.getByRole('img', { name: 'SMA(20) chart' })).toBeInTheDocument();
  });

  it('draws one path per series', () => {
    renderChart(
      [
        { name: 'upper', label: 'Upper', values: [1, 2, 3] },
        { name: 'lower', label: 'Lower', values: [0, 1, 2] },
      ],
      line,
    );
    const svg = screen.getByRole('img');
    expect(svg.querySelectorAll('path')).toHaveLength(2);
  });

  it('shows a legend swatch and label for every series', () => {
    renderChart(
      [
        { name: 'upper', label: 'Upper Band', values: [1, 2, 3] },
        { name: 'lower', label: 'Lower Band', values: [0, 1, 2] },
      ],
      line,
    );
    expect(screen.getByText('Upper Band')).toBeInTheDocument();
    expect(screen.getByText('Lower Band')).toBeInTheDocument();
  });

  it('draws a reference line for an oscillator config', () => {
    renderChart([{ name: 'rsi', label: 'RSI(14)', values: [40, 55, 72] }], {
      kind: 'oscillator',
      domain: [0, 100],
      referenceLines: [
        { value: 30, label: 'Oversold (30)', band: 'low' },
        { value: 70, label: 'Overbought (70)', band: 'high' },
      ],
    });
    const svg = screen.getByRole('img');
    expect(svg.querySelectorAll('line')).toHaveLength(2);
    expect(screen.getByText('Oversold (30)')).toBeInTheDocument();
    expect(screen.getByText('Overbought (70)')).toBeInTheDocument();
  });

  it('shows a placeholder message when nothing can be drawn', () => {
    renderChart([{ name: 'sma', label: 'SMA(20)', values: [null, null] }], line);
    expect(screen.getByText('Not enough data to draw a chart yet.')).toBeInTheDocument();
  });

  it('draws nothing but still renders the svg when the series is empty', () => {
    renderChart([{ name: 'sma', label: 'SMA(20)', values: [] }], line);
    expect(screen.getByRole('img')).toBeInTheDocument();
  });
});
