import { describe, expect, it } from 'vitest';
import { estimateExportBytes, formatBytes, EXPORT_FORMAT_OPTIONS } from './export-format';

describe('EXPORT_FORMAT_OPTIONS', () => {
  it('lists csv and json', () => {
    expect(EXPORT_FORMAT_OPTIONS.map((option) => option.format)).toEqual(['csv', 'json']);
  });
});

describe('estimateExportBytes', () => {
  it('scales with rows and columns', () => {
    const small = estimateExportBytes(10, 5, 'csv');
    const large = estimateExportBytes(100, 5, 'csv');
    expect(large).toBeGreaterThan(small);
  });

  it('accounts for the extra split column', () => {
    // 10 rows * (5 + 1 split column) * bytesPerCell
    const option = EXPORT_FORMAT_OPTIONS.find((entry) => entry.format === 'csv')!;
    expect(estimateExportBytes(10, 5, 'csv')).toBe(10 * 6 * option.bytesPerCellEstimate);
  });

  it('estimates json as larger than csv for the same shape', () => {
    expect(estimateExportBytes(100, 10, 'json')).toBeGreaterThan(
      estimateExportBytes(100, 10, 'csv'),
    );
  });
});

describe('formatBytes', () => {
  it('renders zero and negative sizes as 0 B', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(-5)).toBe('0 B');
  });

  it('renders bytes under 1024 verbatim', () => {
    expect(formatBytes(500)).toBe('500 B');
  });

  it('renders kilobytes', () => {
    expect(formatBytes(2048)).toBe('2 KB');
  });

  it('renders megabytes', () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe('5 MB');
  });
});
