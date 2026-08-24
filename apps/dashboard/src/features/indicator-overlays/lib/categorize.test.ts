import { describe, expect, it } from 'vitest';
import type { Indicator } from '@/types/api/indicators';
import { groupIndicatorsByCategory } from './categorize';

function indicator(overrides: Partial<Indicator> = {}): Indicator {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'Stub.',
    category: 'trend',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: '',
    parameters: [],
    outputs: [],
    ...overrides,
  };
}

describe('groupIndicatorsByCategory', () => {
  it('groups indicators under their category label', () => {
    const groups = groupIndicatorsByCategory([
      indicator({ name: 'sma', category: 'trend' }),
      indicator({ name: 'rsi', label: 'Relative Strength Index', category: 'momentum' }),
    ]);
    expect(groups.map((g) => g.label)).toEqual(['Trend', 'Momentum']);
    expect(groups[0]!.indicators.map((i) => i.name)).toEqual(['sma']);
    expect(groups[1]!.indicators.map((i) => i.name)).toEqual(['rsi']);
  });

  it('orders known categories by the canonical taxonomy, not alphabetically', () => {
    const groups = groupIndicatorsByCategory([
      indicator({ name: 'vol', category: 'volume' }),
      indicator({ name: 'trend-one', category: 'trend' }),
      indicator({ name: 'mom', category: 'momentum' }),
    ]);
    // Trend < Momentum < Volume in the canonical order, even though
    // alphabetically Momentum < Trend < Volume.
    expect(groups.map((g) => g.label)).toEqual(['Trend', 'Momentum', 'Volume']);
  });

  it('puts an uncurated category after every canonical one, title-cased', () => {
    const groups = groupIndicatorsByCategory([
      indicator({ name: 'exotic', category: 'experimental' }),
      indicator({ name: 'sma', category: 'trend' }),
    ]);
    expect(groups.map((g) => g.label)).toEqual(['Trend', 'Experimental']);
  });

  it('matches the category case-insensitively against the canonical taxonomy', () => {
    const groups = groupIndicatorsByCategory([indicator({ category: 'TREND' })]);
    expect(groups[0]!.label).toBe('Trend');
  });

  it('sorts indicators within a category by label', () => {
    const groups = groupIndicatorsByCategory([
      indicator({ name: 'wma', label: 'Weighted Moving Average', category: 'trend' }),
      indicator({ name: 'ema', label: 'Exponential Moving Average', category: 'trend' }),
    ]);
    expect(groups[0]!.indicators.map((i) => i.name)).toEqual(['ema', 'wma']);
  });

  it('returns no groups for an empty indicator list', () => {
    expect(groupIndicatorsByCategory([])).toEqual([]);
  });
});
