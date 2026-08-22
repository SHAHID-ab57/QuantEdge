import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { UTCTimestamp } from 'lightweight-charts';
import { ChartLegend } from './chart-legend';

afterEach(() => {
  cleanup();
});

describe('ChartLegend', () => {
  it('prompts to hover the chart when there is no point', () => {
    render(<ChartLegend point={null} />);
    expect(screen.getByText('Hover the chart for candle details.')).toBeInTheDocument();
  });

  it('renders open, high, low, close, volume, and timestamp', () => {
    render(
      <ChartLegend
        point={{
          time: 1_785_888_000 as UTCTimestamp,
          open: 3000,
          high: 3100,
          low: 2950,
          close: 3055.25,
          volume: 120.5,
        }}
      />,
    );

    const legend = screen.getByLabelText('Candle details at crosshair');
    expect(legend).toHaveTextContent('O');
    expect(legend).toHaveTextContent('3,000.00');
    expect(legend).toHaveTextContent('H');
    expect(legend).toHaveTextContent('3,100.00');
    expect(legend).toHaveTextContent('L');
    expect(legend).toHaveTextContent('2,950.00');
    expect(legend).toHaveTextContent('C');
    expect(legend).toHaveTextContent('3,055.25');
    expect(legend).toHaveTextContent('Vol');
    expect(legend).toHaveTextContent('120.5');
  });

  it('shows a dash for volume when unavailable', () => {
    render(
      <ChartLegend
        point={{
          time: 1_785_888_000 as UTCTimestamp,
          open: 100,
          high: 110,
          low: 90,
          close: 105,
          volume: null,
        }}
      />,
    );
    expect(screen.getByLabelText('Candle details at crosshair')).toHaveTextContent('—');
  });
});
