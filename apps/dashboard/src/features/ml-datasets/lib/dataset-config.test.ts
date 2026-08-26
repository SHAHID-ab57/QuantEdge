import { describe, expect, it } from 'vitest';
import type { DatasetFormValues } from '@/features/feature-engineering/components/dataset-form';
import type { FeatureSelection } from '@/features/feature-engineering/lib/feature-selection';
import { parseDatasetConfig, serializeDatasetConfig } from './dataset-config';
import type { TargetSelection } from './target-selection';

const form: DatasetFormValues = {
  market: 'ETHUSD',
  timeframe: '1h',
  range: 'custom',
  start: '2026-01-01',
  end: '2026-01-31',
  limit: 500,
};

const featureSelections: FeatureSelection[] = [{ feature: 'ohlcv', params: {} }];
const targetSelections: TargetSelection[] = [{ target: 'next_close', params: { horizon: '1' } }];
const split = { train: 0.7, validation: 0.15, test: 0.15 };

describe('serializeDatasetConfig', () => {
  it('captures market, timeframe, range, features, targets, and split', () => {
    const config = serializeDatasetConfig(form, featureSelections, targetSelections, split);
    expect(config).toEqual({
      market: 'ETHUSD',
      timeframe: '1h',
      range: 'custom',
      start: '2026-01-01',
      end: '2026-01-31',
      limit: 500,
      features: [{ feature: 'ohlcv', params: {} }],
      targets: [{ target: 'next_close', params: { horizon: '1' } }],
      split,
    });
  });
});

describe('parseDatasetConfig — round trip', () => {
  it('parses a config serialized by this same module back out identically', () => {
    const config = serializeDatasetConfig(form, featureSelections, targetSelections, split);
    const result = parseDatasetConfig(JSON.stringify(config));
    expect(result).toEqual({ ok: true, config });
  });
});

describe('parseDatasetConfig — invalid input', () => {
  it('rejects text that is not valid JSON', () => {
    const result = parseDatasetConfig('{not json');
    expect(result).toEqual({ ok: false, error: 'That is not valid JSON.' });
  });

  it('rejects a config missing a required field', () => {
    const result = parseDatasetConfig(
      JSON.stringify({ timeframe: '1h', split: { train: 1, validation: 0, test: 0 } }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toMatch(/market/);
    }
  });

  it('rejects a config with the wrong type for a field', () => {
    const result = parseDatasetConfig(
      JSON.stringify({
        market: 'ETHUSD',
        timeframe: '1h',
        split: { train: 'a lot', validation: 0, test: 0 },
      }),
    );
    expect(result.ok).toBe(false);
  });

  it('defaults an omitted range/limit/features/targets to sensible values', () => {
    const result = parseDatasetConfig(
      JSON.stringify({
        market: 'ETHUSD',
        timeframe: '1h',
        split: { train: 1, validation: 0, test: 0 },
      }),
    );
    expect(result).toEqual({
      ok: true,
      config: {
        market: 'ETHUSD',
        timeframe: '1h',
        range: 'all',
        start: '',
        end: '',
        limit: 500,
        features: [],
        targets: [],
        split: { train: 1, validation: 0, test: 0 },
      },
    });
  });
});
