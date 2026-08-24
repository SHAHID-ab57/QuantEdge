import { describe, expect, it } from 'vitest';
import { buildLinePath, computeDomain, yForValue } from './svg-line-path';

describe('computeDomain', () => {
  it('spans the min and max across every series', () => {
    expect(computeDomain([[1, 5, 3]])).toEqual({ min: 1, max: 5 });
  });

  it('spans multiple series together', () => {
    expect(
      computeDomain([
        [1, 2],
        [10, -3],
      ]),
    ).toEqual({ min: -3, max: 10 });
  });

  it('ignores nulls', () => {
    expect(computeDomain([[null, 4, null, 2]])).toEqual({ min: 2, max: 4 });
  });

  it('widens the domain to include extra fixed values', () => {
    expect(computeDomain([[40, 60]], [0, 100])).toEqual({ min: 0, max: 100 });
  });

  it('returns null when every value is null', () => {
    expect(computeDomain([[null, null]])).toBeNull();
  });

  it('returns null for an empty input', () => {
    expect(computeDomain([[]])).toBeNull();
  });
});

describe('buildLinePath', () => {
  const domain = { min: 0, max: 10 };

  it('builds an SVG path starting with M and continuing with L', () => {
    const path = buildLinePath([0, 5, 10], 100, 50, domain);
    expect(path).toMatch(/^M0\.00,50\.00 L50\.00,25\.00 L100\.00,0\.00$/);
  });

  it('skips a null point, connecting the two real points around it', () => {
    // A null at index 1 must not become a plotted point at value 0 (which
    // would be indistinguishable from a real zero reading) — it is simply
    // omitted, so the path goes straight from index 0 to index 2.
    const path = buildLinePath([0, null, 10], 100, 50, domain);
    expect(path).toBe('M0.00,50.00 L100.00,0.00');
  });

  it('returns null when fewer than two points can be plotted', () => {
    expect(buildLinePath([5], 100, 50, domain)).toBeNull();
    expect(buildLinePath([null, null], 100, 50, domain)).toBeNull();
  });

  it('centers a flat line when the domain has zero range', () => {
    const flat = buildLinePath([5, 5, 5], 100, 50, { min: 5, max: 5 });
    expect(flat).toBe('M0.00,25.00 L50.00,25.00 L100.00,25.00');
  });
});

describe('yForValue', () => {
  it('maps the domain minimum to the bottom of the chart', () => {
    expect(yForValue(0, 100, { min: 0, max: 10 })).toBe(100);
  });

  it('maps the domain maximum to the top of the chart', () => {
    expect(yForValue(10, 100, { min: 0, max: 10 })).toBe(0);
  });

  it('maps the midpoint to the vertical center', () => {
    expect(yForValue(5, 100, { min: 0, max: 10 })).toBe(50);
  });

  it('centers a value when the domain has zero range', () => {
    expect(yForValue(7, 100, { min: 7, max: 7 })).toBe(50);
  });
});
