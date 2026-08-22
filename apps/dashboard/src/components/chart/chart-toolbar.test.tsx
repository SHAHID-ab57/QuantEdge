import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Market } from '@/types/api/market';
import { ChartToolbar } from './chart-toolbar';

afterEach(() => {
  cleanup();
});

const markets: Market[] = [
  {
    id: '11111111-1111-4111-8111-111111111112',
    symbol: 'ETHUSD',
    exchange: 'Delta Exchange',
    exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
    base_asset: 'ETH',
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 3136,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.05',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: '2024-02-05T12:04:17Z',
  },
];

describe('ChartToolbar', () => {
  it('shows a read-only market/timeframe label when no selector callbacks are given', () => {
    render(
      <ChartToolbar
        symbol="ETHUSD"
        timeframe="1h"
        onFitContent={vi.fn()}
        candleCount={250}
        truncated={false}
      />,
    );
    expect(screen.getByText('ETHUSD · 1h')).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /select a market/i })).not.toBeInTheDocument();
    expect(screen.getByText('250 candles')).toBeInTheDocument();
  });

  it('renders standalone selectors when markets/timeframes and their handlers are provided', () => {
    render(
      <ChartToolbar
        symbol="ETHUSD"
        timeframe="1h"
        onFitContent={vi.fn()}
        candleCount={10}
        truncated={false}
        markets={markets}
        availableTimeframes={['1h', '4h']}
        onSymbolChange={vi.fn()}
        onTimeframeChange={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('combobox', { name: 'Select a market for the chart' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('group', { name: 'Select a timeframe for the chart' }),
    ).toBeInTheDocument();
  });

  it('calls onFitContent when the fit-to-content button is clicked', () => {
    const onFitContent = vi.fn();
    render(
      <ChartToolbar
        symbol="ETHUSD"
        timeframe="1h"
        onFitContent={onFitContent}
        candleCount={10}
        truncated={false}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Fit chart to content' }));
    expect(onFitContent).toHaveBeenCalledTimes(1);
  });

  it('notes when the dataset was truncated to the most recent candles', () => {
    render(
      <ChartToolbar
        symbol="ETHUSD"
        timeframe="1m"
        onFitContent={vi.fn()}
        candleCount={10_000}
        truncated
      />,
    );
    expect(screen.getByText(/showing the most recent range/i)).toBeInTheDocument();
  });
});
