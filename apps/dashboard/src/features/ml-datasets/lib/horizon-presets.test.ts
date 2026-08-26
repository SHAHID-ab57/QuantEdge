import { describe, expect, it } from 'vitest';
import {
  CUSTOM_HORIZON_VALUE,
  horizonSelectValue,
  horizonSpecFor,
  isPresetValue,
  presetsInRange,
  HORIZON_PRESETS,
} from './horizon-presets';

describe('presetsInRange', () => {
  it('returns every preset when there are no bounds', () => {
    expect(presetsInRange(null, null)).toEqual([...HORIZON_PRESETS]);
  });

  it('excludes presets below the minimum', () => {
    expect(presetsInRange(5, null)).toEqual([5, 10, 20, 50]);
  });

  it('excludes presets above the maximum', () => {
    expect(presetsInRange(null, 10)).toEqual([1, 2, 3, 5, 10]);
  });

  it('applies both bounds together', () => {
    expect(presetsInRange(2, 10)).toEqual([2, 3, 5, 10]);
  });
});

describe('isPresetValue', () => {
  it('matches a preset expressed as a string', () => {
    expect(isPresetValue('5', [1, 5, 10])).toBe(true);
  });

  it('rejects a value outside the preset list', () => {
    expect(isPresetValue('7', [1, 5, 10])).toBe(false);
  });
});

describe('horizonSelectValue', () => {
  it('returns the value itself when it matches a preset', () => {
    expect(horizonSelectValue('5', [1, 5, 10])).toBe('5');
  });

  it('returns the custom sentinel for a non-preset value', () => {
    expect(horizonSelectValue('7', [1, 5, 10])).toBe(CUSTOM_HORIZON_VALUE);
  });

  it('returns the custom sentinel for an empty value', () => {
    expect(horizonSelectValue('', [1, 5, 10])).toBe(CUSTOM_HORIZON_VALUE);
  });
});

describe('horizonSpecFor', () => {
  it('finds the parameter named "horizon"', () => {
    const spec = horizonSpecFor([
      {
        name: 'horizon',
        type: 'int',
        label: 'Horizon',
        description: '',
        default: 1,
        required: false,
        minimum: 1,
        maximum: 500,
        choices: [],
      },
    ]);
    expect(spec?.name).toBe('horizon');
  });

  it('returns undefined when there is no horizon parameter', () => {
    expect(horizonSpecFor([])).toBeUndefined();
  });
});
