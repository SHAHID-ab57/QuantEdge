import { describe, expect, it } from 'vitest';
import { deriveMetricHistory, type MetricSample } from './metric-history';

function sample(overrides: Partial<MetricSample> = {}): MetricSample {
  return {
    timestampMs: 0,
    buyVolume: 1,
    sellVolume: 2,
    tradesPerMinute: 3,
    volumePerMinute: 4,
    vwapOneMinute: 5,
    avgTradeSize: 6,
    ...overrides,
  };
}

describe('deriveMetricHistory', () => {
  it('returns empty arrays for an empty sample list', () => {
    expect(deriveMetricHistory([])).toEqual({
      timestamps: [],
      buyVolume: [],
      sellVolume: [],
      tradesPerMinute: [],
      volumePerMinute: [],
      vwapOneMinute: [],
      avgTradeSize: [],
    });
  });

  it('flattens one field per metric, preserving order', () => {
    const samples = [
      sample({ timestampMs: 1, buyVolume: 10, vwapOneMinute: null }),
      sample({ timestampMs: 2, buyVolume: 20, vwapOneMinute: 99 }),
    ];
    const history = deriveMetricHistory(samples);
    expect(history.timestamps).toEqual([1, 2]);
    expect(history.buyVolume).toEqual([10, 20]);
    expect(history.vwapOneMinute).toEqual([null, 99]);
  });
});
