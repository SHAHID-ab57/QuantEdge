import { describe, expect, it } from 'vitest';
import { csvLine, escapeCsv, sanitizeFilenamePart } from './csv';

describe('escapeCsv', () => {
  it('wraps a plain value in quotes', () => {
    expect(escapeCsv('ETHUSD')).toBe('"ETHUSD"');
  });

  it('doubles an embedded quote', () => {
    expect(escapeCsv('say "hi"')).toBe('"say ""hi"""');
  });
});

describe('csvLine', () => {
  it('joins escaped cells with commas', () => {
    expect(csvLine(['a', 1, 'b,c'])).toBe('"a","1","b,c"');
  });
});

describe('sanitizeFilenamePart', () => {
  it('replaces unsafe characters', () => {
    expect(sanitizeFilenamePart('2026-01-01T00:00:00Z')).toBe('2026-01-01T00-00-00Z');
  });

  it('defaults to "all" for null', () => {
    expect(sanitizeFilenamePart(null)).toBe('all');
  });
});
