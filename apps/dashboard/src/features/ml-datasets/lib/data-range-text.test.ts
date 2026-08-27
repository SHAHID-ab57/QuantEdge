import { describe, expect, it } from 'vitest';
import { dataRangeText, historicalRangeText } from './data-range-text';

describe('dataRangeText', () => {
  it('renders a preset label for a non-custom range', () => {
    expect(dataRangeText({ range: 'all', start: '', end: '' })).toBe('All History');
  });

  it('renders the explicit start–end for a custom range', () => {
    expect(dataRangeText({ range: 'custom', start: '2026-01-01', end: '2026-01-31' })).toBe(
      '2026-01-01 – 2026-01-31',
    );
  });

  it('flags an incomplete custom range', () => {
    expect(dataRangeText({ range: 'custom', start: '', end: '' })).toBe(
      'Custom range (incomplete)',
    );
  });
});

describe('historicalRangeText', () => {
  it('renders a single date when the first and last timestamp fall on the same day', () => {
    const text = historicalRangeText(['2026-01-01T00:00:00Z', '2026-01-01T05:00:00Z']);
    expect(text).toBe(new Date('2026-01-01T00:00:00Z').toLocaleDateString());
  });

  it('renders a first – last range across different days', () => {
    const text = historicalRangeText(['2026-01-01T00:00:00Z', '2026-01-10T00:00:00Z']);
    const first = new Date('2026-01-01T00:00:00Z').toLocaleDateString();
    const last = new Date('2026-01-10T00:00:00Z').toLocaleDateString();
    expect(text).toBe(`${first} – ${last}`);
  });

  it('reports no rows for an empty timestamp list', () => {
    expect(historicalRangeText([])).toBe('No rows');
  });
});
