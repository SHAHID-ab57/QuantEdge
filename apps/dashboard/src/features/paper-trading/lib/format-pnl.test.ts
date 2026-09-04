import { describe, expect, it } from 'vitest';
import { formatSignedCurrency } from './format-pnl';

describe('formatSignedCurrency', () => {
  it('puts a leading plus sign before the dollar sign for a positive value', () => {
    expect(formatSignedCurrency(995)).toBe('+$995.00');
  });

  it('puts a leading minus sign before the dollar sign for a negative value', () => {
    expect(formatSignedCurrency(-50)).toBe('-$50.00');
  });

  it('has no sign at all for exactly zero', () => {
    expect(formatSignedCurrency(0)).toBe('$0.00');
  });

  it('rounds to exactly two decimal places', () => {
    expect(formatSignedCurrency(978.5055)).toBe('+$978.51');
  });
});
