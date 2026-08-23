import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { TradeRecord } from '../lib/trade-record';
import { LargestTradeCard } from './largest-trade-card';

afterEach(() => {
  cleanup();
});

function record(overrides: Partial<TradeRecord> = {}): TradeRecord {
  return {
    price: 100,
    size: 2,
    value: 200,
    side: 'buy',
    timestampMs: Date.parse('2026-01-01T00:00:00Z'),
    ...overrides,
  };
}

describe('LargestTradeCard', () => {
  it('shows Unavailable when there is no trade yet', () => {
    render(<LargestTradeCard title="Largest Trade — Session" trade={null} />);
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
  });

  it('shows Time, Side, Price, Quantity, and Value for a trade', () => {
    render(<LargestTradeCard title="Largest Trade — Session" trade={record()} />);
    for (const label of ['Time', 'Side', 'Price', 'Quantity', 'Value']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('Buy')).toBeInTheDocument();
    expect(screen.getByText('200.00')).toBeInTheDocument();
  });

  it('renders the given title', () => {
    render(<LargestTradeCard title="Largest Trade — Last Minute" trade={record()} />);
    expect(screen.getByText('Largest Trade — Last Minute')).toBeInTheDocument();
  });
});
