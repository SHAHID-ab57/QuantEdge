import { describe, expect, it } from 'vitest';
import { groupByCategory, type CategoryOrderEntry } from './group-by-category';

interface Entry {
  name: string;
  label: string;
  category: string;
}

function entry(name: string, category: string, label = name.toUpperCase()): Entry {
  return { name, label, category };
}

const ORDER: readonly CategoryOrderEntry[] = [
  { key: 'trend', label: 'Trend' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'volume', label: 'Volume' },
];

describe('groupByCategory', () => {
  it('groups entries under their curated label', () => {
    const groups = groupByCategory([entry('sma', 'trend'), entry('rsi', 'momentum')], ORDER);
    expect(groups.map((g) => g.label)).toEqual(['Trend', 'Momentum']);
    expect(groups[0]!.items.map((i) => i.name)).toEqual(['sma']);
  });

  it('orders by the curated taxonomy, not alphabetically', () => {
    const groups = groupByCategory(
      [entry('a', 'volume'), entry('b', 'trend'), entry('c', 'momentum')],
      ORDER,
    );
    // Alphabetically this would be momentum, trend, volume.
    expect(groups.map((g) => g.label)).toEqual(['Trend', 'Momentum', 'Volume']);
  });

  it('matches a category case-insensitively', () => {
    const groups = groupByCategory([entry('a', 'TREND')], ORDER);
    expect(groups[0]!.label).toBe('Trend');
  });

  it('places an uncurated category after every curated one', () => {
    const groups = groupByCategory([entry('x', 'experimental'), entry('s', 'trend')], ORDER);
    expect(groups.map((g) => g.label)).toEqual(['Trend', 'Experimental']);
  });

  it('sorts several uncurated categories alphabetically', () => {
    const groups = groupByCategory([entry('z', 'zeta'), entry('a', 'alpha')], ORDER);
    expect(groups.map((g) => g.label)).toEqual(['Alpha', 'Zeta']);
  });

  it('title-cases a snake_case category so it reads as a heading', () => {
    // The fallback is load-bearing: a brand-new backend category must
    // render as a readable section with no frontend change.
    const groups = groupByCategory([entry('a', 'price_action')], ORDER);
    expect(groups[0]!.label).toBe('Price Action');
  });

  it('sorts entries within a group by label', () => {
    const groups = groupByCategory(
      [entry('w', 'trend', 'Weighted'), entry('e', 'trend', 'Exponential')],
      ORDER,
    );
    expect(groups[0]!.items.map((i) => i.label)).toEqual(['Exponential', 'Weighted']);
  });

  it('exposes the raw backend category as the group key', () => {
    const groups = groupByCategory([entry('a', 'price_action')], ORDER);
    expect(groups[0]!.key).toBe('price_action');
  });

  it('returns no groups for an empty list', () => {
    expect(groupByCategory([], ORDER)).toEqual([]);
  });

  it('handles an empty category string without crashing', () => {
    const groups = groupByCategory([entry('a', '')], ORDER);
    expect(groups[0]!.label).toBe('Other');
  });
});
