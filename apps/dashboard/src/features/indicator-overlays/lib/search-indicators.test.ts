import { describe, expect, it } from 'vitest';
import type { Indicator } from '@/types/api/indicators';
import { matchesIndicatorSearch } from './search-indicators';

function indicator(overrides: Partial<Indicator> = {}): Indicator {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'The unweighted mean of the last N values.',
    category: 'trend',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: '',
    parameters: [],
    outputs: [],
    aliases: ['MA', 'Moving Average'],
    ...overrides,
  };
}

describe('matchesIndicatorSearch', () => {
  it('matches an empty query against everything', () => {
    expect(matchesIndicatorSearch(indicator(), '')).toBe(true);
    expect(matchesIndicatorSearch(indicator(), '   ')).toBe(true);
  });

  it('matches by name', () => {
    expect(matchesIndicatorSearch(indicator(), 'sma')).toBe(true);
  });

  it('matches by label, case-insensitively', () => {
    expect(matchesIndicatorSearch(indicator(), 'SIMPLE moving')).toBe(true);
  });

  it('matches by category', () => {
    expect(matchesIndicatorSearch(indicator({ category: 'momentum' }), 'momentum')).toBe(true);
  });

  it('matches by an alias not present in the name or label', () => {
    expect(matchesIndicatorSearch(indicator({ aliases: ['MA'] }), 'ma')).toBe(true);
  });

  it('matches by description', () => {
    expect(matchesIndicatorSearch(indicator(), 'unweighted mean')).toBe(true);
  });

  it('does not match an unrelated query', () => {
    expect(matchesIndicatorSearch(indicator(), 'bollinger')).toBe(false);
  });

  it('treats a missing aliases field as no aliases, without throwing', () => {
    const withoutAliases = indicator({ aliases: undefined });
    expect(matchesIndicatorSearch(withoutAliases, 'sma')).toBe(true);
    expect(matchesIndicatorSearch(withoutAliases, 'nonexistent')).toBe(false);
  });
});
