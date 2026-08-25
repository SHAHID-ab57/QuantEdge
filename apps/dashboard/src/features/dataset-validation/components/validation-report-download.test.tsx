import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import * as downloadFile from '@/lib/download-file';
import type { ValidationReport } from '@/types/api/dataset-validation';
import { ValidationReportDownload } from './validation-report-download';

vi.mock('@/lib/download-file', () => ({ downloadBlob: vi.fn() }));

const mockedDownload = vi.mocked(downloadFile);

function report(): ValidationReport {
  return {
    dataset_id: 'abc',
    symbol: 'ETHUSD',
    timeframe: '1h',
    engine_version: '1.0.0',
    validated_at: '2026-01-01T02:03:04Z',
    passed: true,
    rules_run: [],
    summary: { total_checks: 0, errors: 0, warnings: 0, info: 0 },
    categories: {},
    issues: [],
    rows: 1,
    columns: 1,
    duration_ms: 0.1,
  };
}

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: vi.fn(() => 'blob:mock'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ValidationReportDownload', () => {
  it('downloads the report as a JSON blob named for the symbol and timeframe', () => {
    render(
      <ThemeProvider theme={theme}>
        <ValidationReportDownload report={report()} />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Download validation report as JSON' }));

    expect(mockedDownload.downloadBlob).toHaveBeenCalledTimes(1);
    const [blob, filename] = mockedDownload.downloadBlob.mock.calls[0]! as [Blob, string];
    expect(blob.type).toBe('application/json');
    expect(filename).toBe('ETHUSD-1h-validation-20260101020304.json');
  });
});
