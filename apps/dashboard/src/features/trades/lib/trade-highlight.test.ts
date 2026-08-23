import { describe, expect, it } from 'vitest';
import { isLargeTrade, LARGE_TRADE_MULTIPLIER } from './trade-highlight';

describe('isLargeTrade', () => {
  it('is false with no baseline average yet', () => {
    expect(isLargeTrade(1_000_000, null)).toBe(false);
  });

  it('is false with a zero or negative average', () => {
    expect(isLargeTrade(100, 0)).toBe(false);
    expect(isLargeTrade(100, -5)).toBe(false);
  });

  it(`is false below ${LARGE_TRADE_MULTIPLIER}x the average`, () => {
    expect(isLargeTrade(100 * LARGE_TRADE_MULTIPLIER - 1, 100)).toBe(false);
  });

  it(`is true at or above ${LARGE_TRADE_MULTIPLIER}x the average`, () => {
    expect(isLargeTrade(100 * LARGE_TRADE_MULTIPLIER, 100)).toBe(true);
    expect(isLargeTrade(100 * LARGE_TRADE_MULTIPLIER + 1, 100)).toBe(true);
  });
});
