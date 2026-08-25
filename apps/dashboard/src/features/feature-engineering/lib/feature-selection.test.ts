import { describe, expect, it } from 'vitest';
import type { Feature } from '@/types/api/features';
import {
  defaultParamsFor,
  formatCell,
  groupFeaturesByCategory,
  isSelected,
  paramSummary,
  toRequestBodies,
  toggleSelection,
  updateSelectionParams,
  type FeatureSelection,
} from './feature-selection';

function feature(overrides: Partial<Feature> = {}): Feature {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'Rolling mean.',
    category: 'trend',
    parameters: [
      {
        name: 'period',
        type: 'int',
        label: 'Period',
        description: 'Window size.',
        default: 20,
        required: false,
        minimum: 1,
        maximum: 1000,
        choices: [],
      },
      {
        name: 'source',
        type: 'string',
        label: 'Source',
        description: 'Price field.',
        default: 'close',
        required: false,
        minimum: null,
        maximum: null,
        choices: ['open', 'high', 'low', 'close'],
      },
    ],
    outputs: ['sma_{period}'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period.',
    ...overrides,
  };
}

function selection(overrides: Partial<FeatureSelection> = {}): FeatureSelection {
  return { feature: 'sma', params: { period: '20' }, ...overrides };
}

describe('defaultParamsFor', () => {
  it('seeds every parameter from the published default', () => {
    // Read from the catalogue, never hardcoded — that is what lets a new
    // backend generator work here with no frontend change.
    expect(defaultParamsFor(feature())).toEqual({ period: '20', source: 'close' });
  });

  it('stringifies defaults so they match the request shape', () => {
    expect(defaultParamsFor(feature())['period']).toBe('20');
  });

  it('omits a required parameter that has no default', () => {
    const required = feature({
      parameters: [
        {
          name: 'window',
          type: 'int',
          label: 'Window',
          description: '',
          default: null,
          required: true,
          minimum: null,
          maximum: null,
          choices: [],
        },
      ],
    });
    expect(defaultParamsFor(required)).toEqual({});
  });

  it('returns an empty map for a parameterless generator', () => {
    expect(defaultParamsFor(feature({ parameters: [] }))).toEqual({});
  });
});

describe('toggleSelection', () => {
  it('adds an unselected feature with its default parameters', () => {
    const next = toggleSelection([], feature());
    expect(next).toHaveLength(1);
    expect(next[0]!.feature).toBe('sma');
    expect(next[0]!.params).toEqual({ period: '20', source: 'close' });
  });

  it('removes an already-selected feature', () => {
    const next = toggleSelection([selection()], feature());
    expect(next).toEqual([]);
  });

  it('preserves the order of other selections', () => {
    const existing = [selection({ feature: 'ohlcv', params: {} }), selection()];
    const next = toggleSelection(existing, feature({ name: 'ema' }));
    expect(next.map((s) => s.feature)).toEqual(['ohlcv', 'sma', 'ema']);
  });

  it('does not mutate the input', () => {
    const existing = [selection()];
    toggleSelection(existing, feature({ name: 'ema' }));
    expect(existing).toHaveLength(1);
  });
});

describe('updateSelectionParams', () => {
  it('replaces the targeted selection’s parameters', () => {
    const next = updateSelectionParams([selection()], 'sma', { period: '50' });
    expect(next[0]!.params).toEqual({ period: '50' });
  });

  it('leaves other selections untouched', () => {
    const existing = [selection(), selection({ feature: 'ema', params: { period: '12' } })];
    const next = updateSelectionParams(existing, 'sma', { period: '50' });
    expect(next[1]!.params).toEqual({ period: '12' });
  });

  it('is a no-op for an unknown feature', () => {
    const next = updateSelectionParams([selection()], 'nope', { period: '5' });
    expect(next[0]!.params).toEqual({ period: '20' });
  });
});

describe('isSelected', () => {
  it('reports membership', () => {
    expect(isSelected([selection()], 'sma')).toBe(true);
    expect(isSelected([selection()], 'ema')).toBe(false);
  });
});

describe('toRequestBodies', () => {
  it('maps selections onto the API request shape', () => {
    expect(toRequestBodies([selection()])).toEqual([{ feature: 'sma', params: { period: '20' } }]);
  });

  it('preserves selection order, which becomes column order', () => {
    const bodies = toRequestBodies([selection({ feature: 'ohlcv', params: {} }), selection()]);
    expect(bodies.map((b) => b.feature)).toEqual(['ohlcv', 'sma']);
  });
});

describe('groupFeaturesByCategory', () => {
  it('puts raw market data before derived families', () => {
    const groups = groupFeaturesByCategory([
      feature({ name: 'sma', category: 'trend' }),
      feature({ name: 'ohlcv', label: 'OHLCV', category: 'raw' }),
    ]);
    expect(groups.map((g) => g.label)).toEqual(['Raw Market Data', 'Trend']);
  });

  it('labels the price_action category readably', () => {
    const groups = groupFeaturesByCategory([
      feature({ name: 'candle_shape', category: 'price_action' }),
    ]);
    expect(groups[0]!.label).toBe('Price Action');
  });

  it('still renders a category nobody has taxonomized', () => {
    const groups = groupFeaturesByCategory([feature({ name: 'x', category: 'experimental' })]);
    expect(groups[0]!.label).toBe('Experimental');
    expect(groups[0]!.features).toHaveLength(1);
  });
});

describe('formatCell', () => {
  it('renders null as an em dash so a gap is visibly a gap', () => {
    expect(formatCell(null)).toBe('—');
  });

  it('renders an integer verbatim', () => {
    expect(formatCell(42)).toBe('42');
  });

  it('trims a float to six significant digits', () => {
    expect(formatCell(3.14159265358979)).toBe('3.14159');
  });

  it('does not pad a short float', () => {
    expect(formatCell(0.5)).toBe('0.5');
  });

  it('renders a categorical verbatim', () => {
    expect(formatCell('up')).toBe('up');
  });

  it('renders a boolean as text', () => {
    expect(formatCell(true)).toBe('true');
    expect(formatCell(false)).toBe('false');
  });

  it('handles a large float without switching to exponent notation', () => {
    expect(formatCell(123456.7)).toBe('123457');
  });
});

describe('paramSummary', () => {
  it('renders key=value pairs', () => {
    expect(paramSummary(selection({ params: { period: '20', source: 'close' } }))).toBe(
      'period=20, source=close',
    );
  });

  it('says so when there are no parameters', () => {
    expect(paramSummary(selection({ params: {} }))).toBe('no parameters');
  });
});
