import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Market } from '@/types/api/market';
import { MarketSelector } from './market-selector';
import { TimeframeSelector } from './timeframe-selector';

afterEach(() => {
  cleanup();
});

const markets: Market[] = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    symbol: 'BTCUSD',
    exchange: 'Delta Exchange',
    exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
    base_asset: 'BTC',
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 27,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.5',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: '2023-12-18T13:10:39Z',
  },
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

describe('MarketSelector', () => {
  it('lists every market from the markets prop with no hardcoded symbols', async () => {
    const onChange = vi.fn();
    render(<MarketSelector markets={markets} value="BTCUSD" onChange={onChange} />);

    const input = screen.getByRole('combobox', { name: 'Select a market for the chart' });
    fireEvent.mouseDown(input);
    expect(screen.getByRole('option', { name: 'BTCUSD' })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));

    expect(onChange).toHaveBeenCalledWith('ETHUSD');
  });
});

describe('TimeframeSelector', () => {
  it('renders one toggle per available timeframe and reports the selection', () => {
    const onChange = vi.fn();
    render(<TimeframeSelector timeframes={['1m', '5m', '1h']} value="1m" onChange={onChange} />);

    const group = screen.getByRole('group', { name: 'Select a timeframe for the chart' });
    expect(group).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '1h' }));

    expect(onChange).toHaveBeenCalledWith('1h');
  });

  it('ignores a click that would deselect the active timeframe', () => {
    const onChange = vi.fn();
    render(<TimeframeSelector timeframes={['1m', '5m']} value="1m" onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: '1m' }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
