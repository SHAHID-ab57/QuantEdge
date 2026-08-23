import { describe, expect, it } from 'vitest';
import { computeVwapDistance } from './vwap-distance';

describe('computeVwapDistance', () => {
  it('returns null before there is a price or a VWAP to compare against', () => {
    expect(computeVwapDistance(null, 100)).toBeNull();
    expect(computeVwapDistance(100, null)).toBeNull();
    expect(computeVwapDistance(null, null)).toBeNull();
  });

  it('returns null rather than Infinity for a zero VWAP', () => {
    expect(computeVwapDistance(100, 0)).toBeNull();
  });

  it('reports a positive distance when trading above VWAP', () => {
    const distance = computeVwapDistance(110, 100);
    expect(distance?.absolute).toBe(10);
    expect(distance?.fraction).toBeCloseTo(0.1);
  });

  it('reports a negative distance when trading below VWAP', () => {
    const distance = computeVwapDistance(90, 100);
    expect(distance?.absolute).toBe(-10);
    expect(distance?.fraction).toBeCloseTo(-0.1);
  });

  it('reports exactly zero when price sits on VWAP', () => {
    expect(computeVwapDistance(100, 100)).toEqual({ absolute: 0, fraction: 0 });
  });
});
