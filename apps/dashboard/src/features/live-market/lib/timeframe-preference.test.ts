import { describe, expect, it } from 'vitest';
import { resolveTimeframe } from './timeframe-preference';

const available = ['5m', '1h', '1d'];

describe('resolveTimeframe', () => {
  it('honours an explicit in-session selection', () => {
    expect(resolveTimeframe({ selected: '1d', requested: '1h', remembered: '5m', available })).toBe(
      '1d',
    );
  });

  it('falls back to the URL request, then the remembered value', () => {
    expect(resolveTimeframe({ selected: null, requested: '1h', remembered: '5m', available })).toBe(
      '1h',
    );
    expect(resolveTimeframe({ selected: null, requested: null, remembered: '5m', available })).toBe(
      '5m',
    );
  });

  it('ignores a candidate the current market has no candles for', () => {
    // A remembered 4h must not blank the chart on a market that lacks it.
    expect(resolveTimeframe({ selected: null, requested: '4h', remembered: '4h', available })).toBe(
      '5m',
    );
  });

  it('defaults to the finest available timeframe for a live view', () => {
    expect(resolveTimeframe({ selected: null, requested: null, remembered: null, available })).toBe(
      '5m',
    );
    expect(
      resolveTimeframe({
        selected: null,
        requested: null,
        remembered: null,
        available: ['1h', '1m'],
      }),
    ).toBe('1m');
  });

  it('falls back to whatever exists when no preferred timeframe is available', () => {
    expect(
      resolveTimeframe({ selected: null, requested: null, remembered: null, available: ['3w'] }),
    ).toBe('3w');
  });

  it('returns null when the market has no timeframes at all', () => {
    expect(
      resolveTimeframe({ selected: '1h', requested: null, remembered: null, available: [] }),
    ).toBeNull();
  });
});
