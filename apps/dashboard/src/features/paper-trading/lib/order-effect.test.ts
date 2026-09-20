import { describe, expect, it } from 'vitest';
import type { PaperPosition } from '@/types/api/paper-trading';
import { describeOrderEffect, effectSentence } from './order-effect';

function position(overrides: Partial<PaperPosition> = {}): PaperPosition {
  return {
    symbol: 'ETHUSD',
    side: 'long',
    quantity: '2',
    average_entry_price: '2000',
    leverage: '1',
    margin: '4000',
    liquidation_price: null,
    liquidation_distance_pct: null,
    current_price: '2000',
    price_source: 'ticker',
    unrealized_pnl: '0',
    stop_loss_price: null,
    take_profit_price: null,
    ...overrides,
  };
}

describe('describeOrderEffect', () => {
  it('opens a long on a buy and a short on a sell when nothing is held', () => {
    expect(describeOrderEffect('buy', 1, undefined)).toEqual({
      kind: 'open',
      positionSide: 'long',
      held: 0,
    });
    expect(describeOrderEffect('sell', 1, undefined)).toEqual({
      kind: 'open',
      positionSide: 'short',
      held: 0,
    });
  });

  it('adds to a position on the same side', () => {
    expect(describeOrderEffect('buy', 1, position()).kind).toBe('add');
    expect(describeOrderEffect('sell', 1, position({ side: 'short' })).kind).toBe('add');
  });

  it('reduces a long with a sell and a short with a buy, up to the held quantity', () => {
    expect(describeOrderEffect('sell', 1, position())).toMatchObject({
      kind: 'reduce',
      positionSide: 'long',
    });
    expect(describeOrderEffect('sell', 2, position()).kind).toBe('reduce');
    expect(describeOrderEffect('buy', 2, position({ side: 'short' })).kind).toBe('reduce');
  });

  it('flags an order larger than the position it reduces as a flip', () => {
    expect(describeOrderEffect('sell', 3, position()).kind).toBe('flip');
    expect(describeOrderEffect('buy', 2.5, position({ side: 'short' })).kind).toBe('flip');
  });

  it('treats an unparseable quantity as a plain reduce rather than a flip', () => {
    expect(describeOrderEffect('sell', Number.NaN, position()).kind).toBe('reduce');
  });
});

describe('effectSentence', () => {
  it('names what the order does in plain language', () => {
    expect(effectSentence({ kind: 'open', positionSide: 'short', held: 0 }, 'ETHUSD')).toBe(
      'Opens a new short position in ETHUSD.',
    );
    expect(effectSentence({ kind: 'add', positionSide: 'long', held: 2 }, 'ETHUSD')).toBe(
      'Adds to your long position in ETHUSD.',
    );
    expect(effectSentence({ kind: 'reduce', positionSide: 'long', held: 2 }, 'ETHUSD')).toBe(
      'Reduces your long position in ETHUSD.',
    );
  });

  it('explains why a flip is refused', () => {
    expect(effectSentence({ kind: 'flip', positionSide: 'long', held: 2 }, 'ETHUSD')).toContain(
      "can't flip a position through zero",
    );
  });
});
