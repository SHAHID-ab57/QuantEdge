import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MarketReadiness } from '../lib/market-selection';
import { MarketDataNotice } from './market-data-notice';

afterEach(() => {
  cleanup();
});

const NOW = Date.parse('2026-01-01T12:00:00Z');

function readiness(overrides: Partial<MarketReadiness> = {}): MarketReadiness {
  return {
    symbol: 'ETHUSD',
    hasHistoricalCandles: true,
    hasLiveSupport: true,
    hasLatestPrice: true,
    isPending: false,
    isReady: true,
    blockers: [],
    ...overrides,
  };
}

function renderNotice(props: Partial<React.ComponentProps<typeof MarketDataNotice>> = {}) {
  return render(
    <MarketDataNotice
      symbol="ETHUSD"
      readiness={readiness()}
      connectionState="open"
      lastMessageAt={NOW - 2_000}
      hasPrice
      now={NOW}
      onRetry={vi.fn()}
      {...props}
    />,
  );
}

describe('MarketDataNotice', () => {
  it('renders nothing for a healthy market that has a price', () => {
    const { container } = renderNotice();
    expect(container).toBeEmptyDOMElement();
  });

  it('explains a missing history and a missing live feed separately', () => {
    renderNotice({
      readiness: readiness({
        hasHistoricalCandles: false,
        hasLiveSupport: false,
        isReady: false,
        blockers: ['No historical candles have been synchronized for this market.', 'not on feed'],
      }),
      hasPrice: false,
    });
    const notice = screen.getByLabelText('Data availability for ETHUSD');
    expect(notice).toHaveTextContent('No data is available for ETHUSD');
    expect(notice).toHaveTextContent(/No historical candles/);
  });

  it('says the stream is connected but silent when only the price is missing', () => {
    renderNotice({ hasPrice: false });
    expect(screen.getByLabelText('Data availability for ETHUSD')).toHaveTextContent(
      /connected; no price has been received/,
    );
  });

  it('reports an automatic reconnect in progress', () => {
    renderNotice({ hasPrice: false, connectionState: 'reconnecting' });
    expect(screen.getByLabelText('Data availability for ETHUSD')).toHaveTextContent(
      /dropped and is reconnecting automatically/,
    );
  });

  it('reports when the last stream message arrived', () => {
    renderNotice({ hasPrice: false });
    expect(screen.getByLabelText('Data availability for ETHUSD')).toHaveTextContent(
      /Last stream message 2\.0s ago/,
    );
  });

  it('says so when no message has ever arrived', () => {
    renderNotice({ hasPrice: false, lastMessageAt: null });
    expect(screen.getByLabelText('Data availability for ETHUSD')).toHaveTextContent(
      /No message has been received on the stream yet/,
    );
  });

  it('offers a retry action', () => {
    const onRetry = vi.fn();
    renderNotice({ hasPrice: false, onRetry });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
