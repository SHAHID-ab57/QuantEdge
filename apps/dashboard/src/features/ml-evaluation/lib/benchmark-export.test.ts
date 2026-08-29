import { describe, expect, it } from 'vitest';
import type { BenchmarkResponse } from '@/types/api/evaluation';
import {
  BENCHMARK_EXPORTERS,
  benchmarkExportFileName,
  buildBenchmarkCsv,
  buildBenchmarkJson,
} from './benchmark-export';

const RESPONSE: BenchmarkResponse = {
  candidates: [
    {
      training_job_id: 'job-a',
      experiment_id: 'exp-1',
      experiment_name: 'Experiment A',
      model_type: 'logistic_regression',
      model_kind: 'classification',
      dataset_version: 'ds-1',
      target_column: 'next_direction',
      completed_at: '2026-01-01T00:00:00Z',
      metrics: { accuracy: 0.8 },
    },
  ],
  best_by_metric: [
    {
      metric: 'accuracy',
      training_job_id: 'job-a',
      model_type: 'logistic_regression',
      value: 0.8,
      higher_is_better: true,
    },
  ],
};

describe('buildBenchmarkCsv', () => {
  it('includes a header row, one data row per candidate, and the best-metric summary', () => {
    const result = buildBenchmarkCsv(RESPONSE);
    expect(result.mimeType).toContain('text/csv');
    expect(result.extension).toBe('csv');
    expect(result.content).toContain('Training Job ID');
    expect(result.content).toContain('job-a');
    expect(result.content).toContain('accuracy');
    expect(result.content).toContain('Best accuracy');
  });
});

describe('buildBenchmarkJson', () => {
  it('serializes the full response verbatim', () => {
    const result = buildBenchmarkJson(RESPONSE);
    expect(result.mimeType).toContain('application/json');
    expect(JSON.parse(result.content)).toEqual(RESPONSE);
  });
});

describe('BENCHMARK_EXPORTERS', () => {
  it('registers csv and json, each buildable from the response', () => {
    expect(Object.keys(BENCHMARK_EXPORTERS)).toEqual(['csv', 'json']);
    for (const format of Object.keys(BENCHMARK_EXPORTERS) as Array<
      keyof typeof BENCHMARK_EXPORTERS
    >) {
      expect(BENCHMARK_EXPORTERS[format].build(RESPONSE).content.length).toBeGreaterThan(0);
    }
  });
});

describe('benchmarkExportFileName', () => {
  it('sanitizes the dataset version and uses the format extension', () => {
    expect(benchmarkExportFileName('csv', 'ds-1')).toBe('benchmark-ds-1.csv');
    expect(benchmarkExportFileName('json', null)).toBe('benchmark-all.json');
  });
});
