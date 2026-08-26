import { describe, expect, it } from 'vitest';
import type { TargetDTO } from '@/types/api/ml-datasets';
import { horizonRangeText, targetProblemType, targetProblemTypeLabel } from './target-type';

function target(overrides: Partial<TargetDTO> = {}): TargetDTO {
  return {
    name: 'next_close',
    label: 'Next Close Price',
    description: '',
    category: 'price',
    parameters: [
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
    ],
    outputs: ['next_close_{horizon}'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    value_type: 'float',
    default_horizon: 1,
    is_deterministic: true,
    ...overrides,
  };
}

describe('targetProblemType', () => {
  it('classifies a categorical value_type as classification', () => {
    expect(targetProblemType({ value_type: 'categorical' })).toBe('classification');
  });

  it('classifies a float value_type as regression', () => {
    expect(targetProblemType({ value_type: 'float' })).toBe('regression');
  });

  it('defaults an unrecognized value_type to regression', () => {
    expect(targetProblemType({ value_type: 'something_else' })).toBe('regression');
  });
});

describe('targetProblemTypeLabel', () => {
  it('labels classification and regression for display', () => {
    expect(targetProblemTypeLabel({ value_type: 'categorical' })).toBe('Classification');
    expect(targetProblemTypeLabel({ value_type: 'float' })).toBe('Regression');
  });
});

describe('horizonRangeText', () => {
  it('describes a bounded range', () => {
    expect(horizonRangeText(target())).toBe('Horizon 1–500 candles ahead');
  });

  it('describes an unbounded maximum', () => {
    const unbounded = target({
      parameters: [
        {
          name: 'horizon',
          type: 'int',
          label: 'Horizon',
          description: '',
          default: 1,
          required: false,
          minimum: 1,
          maximum: null,
          choices: [],
        },
      ],
    });
    expect(horizonRangeText(unbounded)).toBe('Horizon 1+ candles ahead');
  });

  it('falls back to a fixed-horizon description when there is no horizon parameter', () => {
    expect(horizonRangeText(target({ parameters: [], default_horizon: 3 }))).toBe(
      'Fixed at 3 candles ahead',
    );
  });
});
