import { describe, expect, it } from 'vitest';
import type { Feature } from '@/types/api/features';
import {
  columnCategoryFor,
  resolvePresetFeatures,
  resolveRequiredColumnOptions,
} from './resolve-required-columns';

function ohlcv(): Feature {
  return {
    name: 'ohlcv',
    label: 'OHLCV',
    description: 'Raw candle fields.',
    category: 'raw',
    parameters: [],
    outputs: ['open', 'high', 'low', 'close', 'volume'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'None.',
  };
}

function sma(): Feature {
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
    ],
    outputs: ['sma_{period}'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period.',
  };
}

function candleShape(): Feature {
  return {
    name: 'candle_shape',
    label: 'Candle Shape',
    description: 'Body, wicks, direction.',
    category: 'price_action',
    parameters: [],
    outputs: ['candle_body', 'upper_wick', 'lower_wick', 'candle_direction'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'None.',
  };
}

describe('columnCategoryFor', () => {
  it('maps raw to Raw Market Data', () => {
    expect(columnCategoryFor('raw')).toBe('Raw Market Data');
  });

  it('maps every indicator-family category to Technical Indicators', () => {
    expect(columnCategoryFor('trend')).toBe('Technical Indicators');
    expect(columnCategoryFor('momentum')).toBe('Technical Indicators');
    expect(columnCategoryFor('volatility')).toBe('Technical Indicators');
    expect(columnCategoryFor('volume')).toBe('Technical Indicators');
  });

  it('maps price_action to Candle Features', () => {
    expect(columnCategoryFor('price_action')).toBe('Candle Features');
  });

  it('maps statistical to Statistical Features', () => {
    expect(columnCategoryFor('statistical')).toBe('Statistical Features');
  });

  it('falls back to Future Features for an unrecognized category', () => {
    expect(columnCategoryFor('something_brand_new')).toBe('Future Features');
  });
});

describe('resolveRequiredColumnOptions', () => {
  it('resolves a template-free output as-is', () => {
    const options = resolveRequiredColumnOptions([ohlcv()], []);
    expect(options.map((option) => option.name)).toEqual([
      'open',
      'high',
      'low',
      'close',
      'volume',
    ]);
  });

  it('resolves a parameterized output using the feature default when unselected', () => {
    const options = resolveRequiredColumnOptions([sma()], []);
    expect(options.map((option) => option.name)).toEqual(['sma_20']);
  });

  it("resolves a parameterized output using the selection's own params when selected", () => {
    const options = resolveRequiredColumnOptions(
      [sma()],
      [{ feature: 'sma', params: { period: '50' } }],
    );
    expect(options.map((option) => option.name)).toEqual(['sma_50']);
  });

  it('tags each option with its resolved category bucket and owning feature', () => {
    const options = resolveRequiredColumnOptions([candleShape()], []);
    expect(options[0]).toMatchObject({
      name: 'candle_body',
      feature: 'candle_shape',
      featureLabel: 'Candle Shape',
      category: 'Candle Features',
    });
  });

  it('deduplicates a column name produced by more than one feature', () => {
    const duplicate: Feature = { ...ohlcv(), name: 'ohlcv_alt', outputs: ['close'] };
    const options = resolveRequiredColumnOptions([ohlcv(), duplicate], []);
    expect(options.filter((option) => option.name === 'close').length).toBe(1);
  });
});

describe('resolvePresetFeatures', () => {
  const catalogue = [ohlcv(), sma(), candleShape()];

  it('raw_market_data selects every raw-category feature', () => {
    expect(resolvePresetFeatures(catalogue, 'raw_market_data').map((f) => f.name)).toEqual([
      'ohlcv',
    ]);
  });

  it('ohlcv_only selects exactly the ohlcv feature', () => {
    expect(resolvePresetFeatures(catalogue, 'ohlcv_only').map((f) => f.name)).toEqual(['ohlcv']);
  });

  it('trend_indicators selects every trend-category feature', () => {
    expect(resolvePresetFeatures(catalogue, 'trend_indicators').map((f) => f.name)).toEqual([
      'sma',
    ]);
  });

  it('ai_basic_features selects the curated starter bundle', () => {
    expect(
      resolvePresetFeatures(catalogue, 'ai_basic_features')
        .map((f) => f.name)
        .sort(),
    ).toEqual(['candle_shape', 'ohlcv', 'sma']);
  });

  it('full_dataset selects every registered feature', () => {
    expect(resolvePresetFeatures(catalogue, 'full_dataset')).toHaveLength(3);
  });

  it('resolves to an empty set when nothing in the catalogue matches', () => {
    expect(resolvePresetFeatures([ohlcv()], 'trend_indicators')).toEqual([]);
  });
});
