import { csvLine, sanitizeFilenamePart } from '@/lib/csv';
import type { BenchmarkResponse } from '@/types/api/evaluation';

/**
 * Benchmark export utilities — deliberately pure (no DOM, no network), the
 * same split `features/indicators/lib/export.ts` already established, so
 * `BenchmarkExportMenu` only has to wire an output to a download side
 * effect. `csvLine`/`sanitizeFilenamePart` are the shared CSV helpers every
 * other export on this platform already uses — no second escaping/quoting
 * implementation.
 */

export type BenchmarkExportFormat = 'csv' | 'json';

export interface BenchmarkExportResult {
  /** A `Blob`-producing exporter (e.g. a future PDF entry) returns a `Blob`
   * here instead of a `string` — `downloadBlob` accepts either uniformly
   * once wrapped, so adding a binary format needs no change to the menu
   * or to `exportBenchmark` below. */
  content: string;
  mimeType: string;
  extension: string;
}

export interface BenchmarkExporter {
  label: string;
  build: (response: BenchmarkResponse) => BenchmarkExportResult;
}

function collectMetricNames(response: BenchmarkResponse): string[] {
  const names = new Set<string>();
  for (const candidate of response.candidates) {
    for (const name of Object.keys(candidate.metrics)) names.add(name);
  }
  return Array.from(names).sort();
}

/**
 * A metadata block (per-metric winners) followed by one data row per
 * candidate — mirroring `features/indicators/lib/export.ts`'s own
 * "metadata block, blank line, then a header + data rows" CSV shape.
 */
export function buildBenchmarkCsv(response: BenchmarkResponse): BenchmarkExportResult {
  const metricNames = collectMetricNames(response);
  const bestLines = response.best_by_metric.map((entry) =>
    csvLine([`Best ${entry.metric}`, entry.model_type, String(entry.value)]),
  );
  const header = csvLine([
    'Training Job ID',
    'Experiment',
    'Model Type',
    'Model Kind',
    'Dataset Version',
    'Target Column',
    'Symbol',
    'Timeframe',
    'Completed At',
    ...metricNames,
  ]);
  const rows = response.candidates.map((candidate) =>
    csvLine([
      candidate.training_job_id,
      candidate.experiment_name,
      candidate.model_type,
      candidate.model_kind,
      candidate.dataset_version ?? '',
      candidate.target_column ?? '',
      candidate.symbol ?? '',
      candidate.timeframe ?? '',
      candidate.completed_at ?? '',
      ...metricNames.map((name) => candidate.metrics[name] ?? ''),
    ]),
  );
  return {
    content: [...bestLines, '', header, ...rows].join('\n'),
    mimeType: 'text/csv;charset=utf-8',
    extension: 'csv',
  };
}

/** The full benchmark response, verbatim — every candidate's complete
 * `report` included, so a JSON export can feed a downstream tool exactly
 * what the comparison page itself saw. */
export function buildBenchmarkJson(response: BenchmarkResponse): BenchmarkExportResult {
  return {
    content: JSON.stringify(response, null, 2),
    mimeType: 'application/json;charset=utf-8',
    extension: 'json',
  };
}

/**
 * The export format registry — this benchmark's own small Strategy +
 * Registry extension point. Adding a future format (e.g. PDF) means adding
 * one entry here; `BenchmarkExportMenu` renders whatever this object
 * contains, never a hardcoded CSV/JSON pair.
 */
export const BENCHMARK_EXPORTERS: Record<BenchmarkExportFormat, BenchmarkExporter> = {
  csv: { label: 'CSV', build: buildBenchmarkCsv },
  json: { label: 'JSON', build: buildBenchmarkJson },
};

export function benchmarkExportFileName(
  format: BenchmarkExportFormat,
  datasetVersion: string | null,
): string {
  // `format` doubles as its own file extension for every exporter registered
  // today (csv, json) — a future format whose extension differs from its
  // registry key (unlikely, but possible for a "pdf-summary" style key)
  // would need this to read `.build(...).extension` instead.
  return `benchmark-${sanitizeFilenamePart(datasetVersion)}.${format}`;
}
