import { describe, expect, it } from 'vitest';
import type { IndicatorParameterSpec } from '@/types/api/indicators';
import { defaultValuesFor, toRequestParams, validateValues } from './parameter-values';

function spec(overrides: Partial<IndicatorParameterSpec> = {}): IndicatorParameterSpec {
  return {
    name: 'period',
    type: 'int',
    label: 'Period',
    description: 'Look-back window.',
    default: 14,
    required: false,
    minimum: 2,
    maximum: 100,
    choices: [],
    ...overrides,
  };
}

describe('defaultValuesFor', () => {
  it('seeds each field from the backend-published default', () => {
    expect(defaultValuesFor([spec()])).toEqual({ period: '14' });
  });

  it('seeds a required parameter as blank rather than a plausible zero', () => {
    // A pre-filled value the researcher never chose is worse than an
    // obviously-empty field.
    expect(defaultValuesFor([spec({ default: null, required: true })])).toEqual({ period: '' });
  });

  it('stringifies non-string defaults, since form state is text', () => {
    expect(defaultValuesFor([spec({ name: 'source', type: 'string', default: 'close' })])).toEqual({
      source: 'close',
    });
  });

  it('returns an empty map for an indicator with no parameters', () => {
    expect(defaultValuesFor([])).toEqual({});
  });
});

describe('toRequestParams', () => {
  it('passes through filled values', () => {
    expect(toRequestParams({ period: '20', source: 'close' })).toEqual({
      period: '20',
      source: 'close',
    });
  });

  it('omits empty values so the backend applies its own default', () => {
    // Sending "" would be rejected as an invalid int; sending nothing gets
    // the documented default.
    expect(toRequestParams({ period: '', source: 'close' })).toEqual({ source: 'close' });
  });

  it('omits whitespace-only values', () => {
    expect(toRequestParams({ period: '   ' })).toEqual({});
  });
});

describe('validateValues', () => {
  it('accepts a value inside the declared bounds', () => {
    expect(validateValues([spec()], { period: '20' })).toEqual({});
  });

  it('accepts values exactly on the inclusive bounds', () => {
    expect(validateValues([spec()], { period: '2' })).toEqual({});
    expect(validateValues([spec()], { period: '100' })).toEqual({});
  });

  it('rejects a value below the minimum', () => {
    expect(validateValues([spec()], { period: '1' })).toEqual({ period: 'Must be at least 2' });
  });

  it('rejects a value above the maximum', () => {
    expect(validateValues([spec()], { period: '101' })).toEqual({ period: 'Must be at most 100' });
  });

  it('rejects a non-numeric value for a numeric parameter', () => {
    expect(validateValues([spec()], { period: 'twenty' })).toEqual({
      period: 'Must be a whole number',
    });
  });

  it('rejects a fractional value for an int parameter', () => {
    expect(validateValues([spec()], { period: '2.5' })).toEqual({
      period: 'Must be a whole number',
    });
  });

  it('accepts a fractional value for a float parameter', () => {
    const float = spec({ type: 'float', minimum: 0, maximum: 10, default: 1 });
    expect(validateValues([float], { period: '2.5' })).toEqual({});
  });

  it('flags a missing required parameter', () => {
    expect(validateValues([spec({ default: null, required: true })], { period: '' })).toEqual({
      period: 'Required',
    });
  });

  it('allows an omitted optional parameter', () => {
    expect(validateValues([spec()], { period: '' })).toEqual({});
  });

  it('rejects a value outside the declared choices', () => {
    const source = spec({
      name: 'source',
      type: 'string',
      default: 'close',
      minimum: null,
      maximum: null,
      choices: ['open', 'close'],
    });
    expect(validateValues([source], { source: 'vwap' })).toEqual({
      source: 'Must be one of: open, close',
    });
  });

  it('accepts a declared choice', () => {
    const source = spec({
      name: 'source',
      type: 'string',
      default: 'close',
      minimum: null,
      maximum: null,
      choices: ['open', 'close'],
    });
    expect(validateValues([source], { source: 'open' })).toEqual({});
  });

  it('reports every offending field at once, not just the first', () => {
    const source = spec({
      name: 'source',
      type: 'string',
      default: 'close',
      minimum: null,
      maximum: null,
      choices: ['open', 'close'],
    });
    expect(validateValues([spec(), source], { period: '0', source: 'vwap' })).toEqual({
      period: 'Must be at least 2',
      source: 'Must be one of: open, close',
    });
  });
});
