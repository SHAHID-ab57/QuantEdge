import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { LiveFundingData, LiveTickerData, LiveTradeData } from '@/types/api/market-stream';
import { PriceCard, UNAVAILABLE, type PriceStats24h } from './price-card';

afterEach(() => {
  cleanup();
});

const NOW = Date.parse('2026-01-01T00:01:00Z');

const trade: LiveTradeData = {
  price: '1900.5',
  size: '2',
  side: 'buy',
  event_time: '2026-01-01T00:00:00Z',
};

const ticker: LiveTickerData = {
  last_price: '1905',
  bid: '1904',
  ask: '1906',
  mark_price: '1905.2',
  open_interest: '17934.2',
  price_change_24h: '3.25',
  event_time: '2026-01-01T00:00:05Z',
};

const funding: LiveFundingData = {
  funding_rate: '-0.0067',
  funding_interval_seconds: 28800,
  next_funding_time: '2026-01-01T08:00:00Z',
  event_time: '2026-01-01T00:00:05Z',
};

const stats: PriceStats24h = {
  highestPrice: '2000',
  lowestPrice: '1800',
  averageVolume: '10',
  totalCandles: 288,
  lastCandleAt: '2026-01-01T00:00:00Z',
};

function renderCard(props: Partial<React.ComponentProps<typeof PriceCard>> = {}) {
  return render(
    <PriceCard
      symbol="ETHUSD"
      latestTrade={null}
      latestTicker={null}
      latestFunding={null}
      stats={undefined}
      statsLoading={false}
      statsError={false}
      now={NOW}
      {...props}
    />,
  );
}

describe('PriceCard', () => {
  it('prefers the ticker last price over the latest trade price', () => {
    renderCard({ latestTrade: trade, latestTicker: ticker });
    expect(screen.getByText('1,905.00')).toBeInTheDocument();
  });

  it('falls back to the latest trade price when there is no ticker yet', () => {
    renderCard({ latestTrade: trade });
    expect(screen.getByText('1,900.50')).toBeInTheDocument();
  });

  it('shows a positive 24h change with a leading plus sign', () => {
    renderCard({ latestTicker: ticker });
    expect(screen.getByText('+3.25%')).toBeInTheDocument();
  });

  it('shows 24h high/low/volume once stats load', () => {
    renderCard({ stats });
    expect(screen.getByText('2,000.00')).toBeInTheDocument();
    expect(screen.getByText('1,800.00')).toBeInTheDocument();
    expect(screen.getByText('2,880')).toBeInTheDocument(); // 10 * 288
  });

  it('reports the last trade and last candle times', () => {
    renderCard({ latestTrade: trade, stats });
    expect(screen.getByText('Last Trade Time')).toBeInTheDocument();
    expect(screen.getByText('Last Candle Time')).toBeInTheDocument();
    // Both timestamps are a minute before `now`.
    expect(screen.getAllByText('1m ago')).toHaveLength(2);
  });

  it('says "Unavailable" rather than a placeholder when nothing has arrived', () => {
    renderCard();
    // Current price, 24h change, high, low, volume, open interest, funding
    // rate, last trade, last candle.
    expect(screen.getAllByText(UNAVAILABLE)).toHaveLength(9);
  });

  it('says "Unavailable" for a non-numeric 24h change instead of rendering NaN', () => {
    renderCard({ latestTicker: { ...ticker, price_change_24h: 'not-a-number' } });
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it('shows a loading skeleton for stats while they are in flight', () => {
    renderCard({ statsLoading: true });
    expect(screen.getByLabelText('Loading 24 hour statistics')).toBeInTheDocument();
  });

  it('marks the stored-candle figures unavailable when stats fail to load', () => {
    renderCard({ statsError: true, latestTicker: ticker, latestTrade: trade });
    // 24h high, 24h low, 24h volume and last candle time all come from stats;
    // funding rate is unavailable too (no funding frame passed here).
    expect(screen.getAllByText(UNAVAILABLE)).toHaveLength(5);
  });

  it('shows open interest from the ticker', () => {
    renderCard({ latestTicker: ticker });
    expect(screen.getByText('Open Interest')).toBeInTheDocument();
    expect(screen.getByText('17,934.20')).toBeInTheDocument();
  });

  // Delta publishes `funding_rate` already in percent (0.01 = 0.01%), so it must be
  // shown as-is. It was once multiplied by 100 again, showing values 100x too large.
  it('renders the funding rate as a signed percentage, as published', () => {
    renderCard({ latestFunding: funding });
    expect(screen.getByText('Funding Rate')).toBeInTheDocument();
    expect(screen.getByText('-0.0067%')).toBeInTheDocument();
    expect(screen.queryByText('-0.6700%')).not.toBeInTheDocument();
  });

  it('does not rescale the funding rate: the 0.01% interest-rate floor shows as 0.0100%', () => {
    renderCard({ latestFunding: { ...funding, funding_rate: '0.01' } });
    expect(screen.getByText('+0.0100%')).toBeInTheDocument();
    expect(screen.queryByText('+1.0000%')).not.toBeInTheDocument();
  });

  it('renders a real live-ticker funding value at its true scale', () => {
    // A real ETHUSD value observed from Delta's ticker: about +0.0017% per 8h, not +0.17%.
    renderCard({ latestFunding: { ...funding, funding_rate: '0.001666603719307179' } });
    expect(screen.getByText('+0.0017%')).toBeInTheDocument();
    expect(screen.queryByText('+0.1667%')).not.toBeInTheDocument();
  });

  it('says "Unavailable" for the funding rate until a funding frame arrives', () => {
    renderCard({ latestTicker: ticker });
    const fundingLabel = screen.getByText('Funding Rate');
    expect(fundingLabel.parentElement).toHaveTextContent(UNAVAILABLE);
  });
});
