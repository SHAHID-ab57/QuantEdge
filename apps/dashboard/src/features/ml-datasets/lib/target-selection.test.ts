import { describe, expect, it } from 'vitest';
import type { TargetDTO } from '@/types/api/ml-datasets';
import {
  defaultParamsForTarget,
  isTargetSelected,
  targetParamSummary,
  toTargetRequestBodies,
  toggleTargetSelection,
  updateTargetSelectionParams,
  type TargetSelection,
} from './target-selection';

function target(overrides: Partial<TargetDTO> = {}): TargetDTO {
  return {
    name: 'next_close',
    label: 'Next Close Price',
    description: 'The close price N candles ahead.',
    category: 'price',
    parameters: [
      {
        name: 'horizon',
        type: 'int',
        label: 'Horizon',
        description: 'Candles ahead.',
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

describe('defaultParamsForTarget', () => {
  it('seeds parameters from the generator’s published defaults', () => {
    expect(defaultParamsForTarget(target())).toEqual({ horizon: '1' });
  });

  it('omits a parameter with no default', () => {
    const noDefault = target({
      parameters: [
        {
          name: 'horizon',
          type: 'int',
          label: 'Horizon',
          description: '',
          default: null,
          required: true,
          minimum: null,
          maximum: null,
          choices: [],
        },
      ],
    });
    expect(defaultParamsForTarget(noDefault)).toEqual({});
  });
});

describe('toggleTargetSelection', () => {
  it('adds a target with its default parameters when not yet selected', () => {
    const next = toggleTargetSelection([], target());
    expect(next).toEqual([{ target: 'next_close', params: { horizon: '1' } }]);
  });

  it('removes a target already selected, preserving order of the rest', () => {
    const selections: TargetSelection[] = [
      { target: 'next_close', params: { horizon: '1' } },
      { target: 'next_return', params: { horizon: '1' } },
    ];
    const next = toggleTargetSelection(selections, target({ name: 'next_close' }));
    expect(next).toEqual([{ target: 'next_return', params: { horizon: '1' } }]);
  });
});

describe('updateTargetSelectionParams', () => {
  it('replaces one selection’s params, leaving the others untouched', () => {
    const selections: TargetSelection[] = [
      { target: 'next_close', params: { horizon: '1' } },
      { target: 'next_return', params: { horizon: '1' } },
    ];
    const next = updateTargetSelectionParams(selections, 'next_close', { horizon: '5' });
    expect(next).toEqual([
      { target: 'next_close', params: { horizon: '5' } },
      { target: 'next_return', params: { horizon: '1' } },
    ]);
  });
});

describe('isTargetSelected', () => {
  it('reports whether a target name is present in the selection list', () => {
    const selections: TargetSelection[] = [{ target: 'next_close', params: {} }];
    expect(isTargetSelected(selections, 'next_close')).toBe(true);
    expect(isTargetSelected(selections, 'next_return')).toBe(false);
  });
});

describe('toTargetRequestBodies', () => {
  it('maps selections onto the API request shape', () => {
    const selections: TargetSelection[] = [{ target: 'next_close', params: { horizon: '3' } }];
    expect(toTargetRequestBodies(selections)).toEqual([
      { target: 'next_close', params: { horizon: '3' } },
    ]);
  });
});

describe('targetParamSummary', () => {
  it('joins parameter key=value pairs', () => {
    expect(targetParamSummary({ target: 'next_close', params: { horizon: '3' } })).toBe(
      'horizon=3',
    );
  });

  it('falls back to a readable default when there are no params', () => {
    expect(targetParamSummary({ target: 'next_close', params: {} })).toBe('default horizon');
  });
});
