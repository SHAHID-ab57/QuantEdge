import { describe, expect, it } from 'vitest';
import { matchesCatalogSearch, type SearchableEntry } from './search-catalog';

function entry(overrides: Partial<SearchableEntry> = {}): SearchableEntry {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    category: 'trend',
    description: 'The unweighted mean of the last N values.',
    aliases: ['MA', 'Moving Average'],
    ...overrides,
  };
}

describe('matchesCatalogSearch', () => {
  it('matches an empty query against everything', () => {
    expect(matchesCatalogSearch(entry(), '')).toBe(true);
    expect(matchesCatalogSearch(entry(), '   ')).toBe(true);
  });

  it('matches by name', () => {
    expect(matchesCatalogSearch(entry(), 'sma')).toBe(true);
  });

  it('matches by label, case-insensitively', () => {
    expect(matchesCatalogSearch(entry(), 'SIMPLE moving')).toBe(true);
  });

  it('matches by category', () => {
    expect(matchesCatalogSearch(entry({ category: 'momentum' }), 'momentum')).toBe(true);
  });

  it('matches by an alias not present in the name or label', () => {
    expect(matchesCatalogSearch(entry({ aliases: ['MA'] }), 'ma')).toBe(true);
  });

  it('matches by description', () => {
    expect(matchesCatalogSearch(entry(), 'unweighted mean')).toBe(true);
  });

  it('does not match an unrelated query', () => {
    expect(matchesCatalogSearch(entry(), 'bollinger')).toBe(false);
  });

  it('treats a missing aliases field as no aliases, without throwing', () => {
    const withoutAliases = entry({ aliases: undefined });
    expect(matchesCatalogSearch(withoutAliases, 'sma')).toBe(true);
    expect(matchesCatalogSearch(withoutAliases, 'nonexistent')).toBe(false);
  });
});
