import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { deriveSentiment } from '../lib/sentiment';
import { MarketSentimentPanel } from './market-sentiment-panel';

afterEach(() => {
  cleanup();
});

describe('MarketSentimentPanel', () => {
  it('shows a Neutral chip with no data yet', () => {
    render(
      <MarketSentimentPanel
        sentiment={deriveSentiment(null)}
        rolling={{ buyVolume: 0, sellVolume: 0 }}
      />,
    );
    expect(screen.getByText('Neutral')).toBeInTheDocument();
  });

  it('shows the Strongly Bullish chip and matching pressure split for one-sided buying', () => {
    render(
      <MarketSentimentPanel
        sentiment={deriveSentiment(1)}
        rolling={{ buyVolume: 10, sellVolume: 0 }}
      />,
    );
    expect(screen.getByText('Strongly Bullish')).toBeInTheDocument();
    expect(screen.getByText('100% / 0%')).toBeInTheDocument();
  });

  it('shows the Strongly Bearish chip for one-sided selling', () => {
    render(
      <MarketSentimentPanel
        sentiment={deriveSentiment(-1)}
        rolling={{ buyVolume: 0, sellVolume: 10 }}
      />,
    );
    expect(screen.getByText('Strongly Bearish')).toBeInTheDocument();
  });
});
