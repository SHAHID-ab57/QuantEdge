import { describe, expect, it } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { toTradeRecord } from './trade-record';

function trade(overrides: Partial<LiveTradeData> = {}): LiveTradeData {
  return {
    price: '100',
    size: '2',
    side: 'buy',
    event_time: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('toTradeRecord', () => {
  it('parses price/size and derives notional value', () => {
    const record = toTradeRecord(trade({ price: '100', size: '2.5' }));
    expect(record).toMatchObject({ price: 100, size: 2.5, value: 250 });
  });

  it('preserves a recognized side', () => {
    expect(toTradeRecord(trade({ side: 'sell' }))?.side).toBe('sell');
  });

  it('degrades an unrecognized side to unknown', () => {
    expect(toTradeRecord(trade({ side: 'bid' }))?.side).toBe('unknown');
  });

  it('parses event_time to epoch milliseconds', () => {
    const record = toTradeRecord(trade({ event_time: '2026-01-01T00:00:01.500Z' }));
    expect(record?.timestampMs).toBe(Date.parse('2026-01-01T00:00:01.500Z'));
  });

  it('returns null for an unparseable price rather than NaN', () => {
    expect(toTradeRecord(trade({ price: 'not-a-number' }))).toBeNull();
  });

  it('returns null for an unparseable size', () => {
    expect(toTradeRecord(trade({ size: 'not-a-number' }))).toBeNull();
  });

  it('returns null for an unparseable timestamp', () => {
    expect(toTradeRecord(trade({ event_time: 'not-a-date' }))).toBeNull();
  });
});
