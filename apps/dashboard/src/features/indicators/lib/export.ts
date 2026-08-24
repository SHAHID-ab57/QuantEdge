import { csvLine, sanitizeFilenamePart } from '@/lib/csv';
import type { IndicatorCalculation } from '@/types/api/indicators';

/**
 * Researcher export utilities for one calculation result. Deliberately
 * pure — no DOM, no clipboard, no network — so `ExportMenu` only has to
 * wire these outputs to a download/clipboard call, and so they're testable
 * without a browser environment.
 */

export function exportFileName(result: IndicatorCalculation, extension: 'csv' | 'json'): string {
  const symbol = sanitizeFilenamePart(result.symbol);
  const indicator = sanitizeFilenamePart(result.indicator.name);
  const timeframe = sanitizeFilenamePart(result.timeframe);
  return `${symbol}-${indicator}-${timeframe}.${extension}`;
}

/** A metadata block followed by one data row per candle, oldest first (the calculation's own order). */
export function buildCsv(result: IndicatorCalculation): string {
  const meta: [string, string][] = [
    ['Market', result.symbol],
    ['Timeframe', result.timeframe],
    ['Indicator', result.indicator.label],
    ['Parameters', JSON.stringify(result.parameters)],
    ['Candles analyzed', String(result.meta.candles_analyzed)],
    ['Warmup candles', String(result.meta.warmup_candles)],
    ['Cache status', result.meta.cache_status],
    ['Generated at', result.meta.generated_at],
  ];
  const metaLines = meta.map(([key, value]) => csvLine([key, value]));
  const header = csvLine(['Timestamp', ...result.series.map((series) => series.label)]);
  const rows = result.timestamps.map((timestamp, index) =>
    csvLine([timestamp, ...result.series.map((series) => series.values[index] ?? '')]),
  );
  return [...metaLines, '', header, ...rows].join('\n');
}

export function buildJson(result: IndicatorCalculation): string {
  return JSON.stringify(result, null, 2);
}

/** Tab-separated values, newest first — matching how the results table itself is displayed. */
export function buildValuesText(result: IndicatorCalculation): string {
  const header = ['Timestamp', ...result.series.map((series) => series.label)].join('\t');
  const rows = result.timestamps
    .map((timestamp, index) => [
      timestamp,
      ...result.series.map((series) => series.values[index] ?? ''),
    ])
    .reverse()
    .map((row) => row.join('\t'));
  return [header, ...rows].join('\n');
}

/**
 * The literal REST URL for the calculation currently on screen, so a
 * researcher can paste it into a terminal or another tool. Built entirely
 * client-side — no request is made — mirroring exactly how
 * `lib/api/indicators.ts`'s `calculateIndicator` assembles its query
 * string, so what's copied always matches what the page actually sent.
 */
export function buildApiRequestUrl(
  baseUrl: string,
  symbol: string,
  indicator: string,
  timeframe: string,
  params: Record<string, string>,
): string {
  const search = new URLSearchParams({ timeframe, ...params });
  const path = `/api/v1/markets/${encodeURIComponent(symbol)}/indicators/${encodeURIComponent(indicator)}`;
  return `${baseUrl.replace(/\/$/, '')}${path}?${search.toString()}`;
}
