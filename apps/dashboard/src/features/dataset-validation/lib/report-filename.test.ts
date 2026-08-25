import { describe, expect, it } from 'vitest';
import type { ValidationReport } from '@/types/api/dataset-validation';
import { reportFilename } from './report-filename';

function report(overrides: Partial<ValidationReport> = {}): ValidationReport {
  return {
    dataset_id: 'abc',
    symbol: 'ETHUSD',
    timeframe: '1h',
    engine_version: '1.0.0',
    validated_at: '2026-01-01T02:03:04Z',
    passed: true,
    rules_run: ['required_columns'],
    summary: { total_checks: 0, errors: 0, warnings: 0, info: 0 },
    categories: {},
    issues: [],
    rows: 10,
    columns: 2,
    duration_ms: 1.2,
    ...overrides,
  };
}

describe('reportFilename', () => {
  it('includes the symbol, timeframe, and a timestamp', () => {
    const name = reportFilename(report());
    expect(name).toBe('ETHUSD-1h-validation-20260101020304.json');
  });

  it('strips characters that are unsafe in a filename', () => {
    const name = reportFilename(report({ symbol: 'ETH/USD' }));
    expect(name).toBe('ETH-USD-1h-validation-20260101020304.json');
  });
});
