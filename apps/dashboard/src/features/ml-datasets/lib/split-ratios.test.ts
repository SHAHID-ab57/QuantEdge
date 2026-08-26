import { describe, expect, it } from 'vitest';
import { validateSplitRatios } from './split-ratios';

describe('validateSplitRatios', () => {
  it('accepts ratios that sum to exactly 1.0', () => {
    expect(validateSplitRatios({ train: 0.7, validation: 0.15, test: 0.15 })).toBeNull();
  });

  it('tolerates IEEE-754 floating-point slack', () => {
    // 0.7 + 0.15 + 0.15 is not bit-exact in floating point.
    expect(validateSplitRatios({ train: 0.7, validation: 0.15, test: 0.15 })).toBeNull();
  });

  it('rejects ratios that do not sum to 1.0', () => {
    expect(validateSplitRatios({ train: 0.5, validation: 0.3, test: 0.3 })).toMatch(/sum to 1\.0/);
  });

  it('rejects a negative ratio', () => {
    expect(validateSplitRatios({ train: 1.1, validation: -0.1, test: 0 })).toMatch(
      /zero or greater/,
    );
  });

  it('rejects a zero train ratio', () => {
    expect(validateSplitRatios({ train: 0, validation: 0.5, test: 0.5 })).toMatch(
      /train ratio must be greater than zero/,
    );
  });

  it('allows a zero validation or test ratio', () => {
    expect(validateSplitRatios({ train: 1, validation: 0, test: 0 })).toBeNull();
  });

  it('rejects a non-finite ratio', () => {
    expect(validateSplitRatios({ train: Number.NaN, validation: 0.5, test: 0.5 })).toMatch(
      /zero or greater/,
    );
  });
});
