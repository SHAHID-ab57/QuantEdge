import { csvLine, sanitizeFilenamePart } from '@/lib/csv';
import type { OverlayChartSeries } from './overlay-series';

/**
 * Export utilities for the *current overlay set* on a chart — CSV, JSON,
 * and a clipboard-friendly values table — mirroring
 * `features/indicators/lib/export.ts`'s pure, DOM-free shape for the
 * standalone `/indicators` page's single-calculation export, but combining
 * several simultaneously-rendered overlays into one aligned table instead
 * of exporting one indicator at a time.
 */

export interface OverlayExportContext {
  symbol: string;
  timeframe: string;
  overlays: OverlayChartSeries[];
}

export function overlayExportFileName(symbol: string, extension: 'csv' | 'json'): string {
  return `${sanitizeFilenamePart(symbol)}-overlays.${extension}`;
}

/** Every distinct time present across any overlay, ascending — overlays don't all share one warmup, so a flat table must union them rather than assume identical timestamps. */
function unionTimes(overlays: OverlayChartSeries[]): number[] {
  const times = new Set<number>();
  for (const overlay of overlays) {
    for (const point of overlay.data) {
      times.add(Number(point.time));
    }
  }
  return Array.from(times).sort((a, b) => a - b);
}

function isoFromUnixSeconds(time: number): string {
  return new Date(time * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export function buildOverlayCsv({ symbol, timeframe, overlays }: OverlayExportContext): string {
  const ok = overlays.filter((overlay) => overlay.ok);
  const failed = overlays.filter((overlay) => !overlay.ok);

  const meta: [string, string][] = [
    ['Market', symbol],
    ['Timeframe', timeframe],
    ['Overlays', String(overlays.length)],
    ...ok.map((overlay): [string, string] => [`${overlay.label} status`, 'ok']),
    ...failed.map((overlay): [string, string] => [
      `${overlay.label} status`,
      overlay.error ?? 'failed',
    ]),
  ];
  const metaLines = meta.map(([key, value]) => csvLine([key, value]));

  const times = unionTimes(ok);
  const valueByOverlayAndTime = ok.map(
    (overlay) => new Map(overlay.data.map((point) => [Number(point.time), point.value])),
  );
  const header = csvLine(['Timestamp', ...ok.map((overlay) => overlay.label)]);
  const rows = times.map((time) =>
    csvLine([
      isoFromUnixSeconds(time),
      ...valueByOverlayAndTime.map((values) => values.get(time) ?? ''),
    ]),
  );

  return [...metaLines, '', header, ...rows].join('\n');
}

export function buildOverlayJson({ symbol, timeframe, overlays }: OverlayExportContext): string {
  const payload = {
    symbol,
    timeframe,
    overlays: overlays.map((overlay) => ({
      id: overlay.id,
      label: overlay.label,
      ok: overlay.ok,
      error: overlay.error ?? null,
      meta: overlay.meta ?? null,
      series: overlay.data.map((point) => ({
        time: isoFromUnixSeconds(Number(point.time)),
        value: point.value,
      })),
    })),
  };
  return JSON.stringify(payload, null, 2);
}

/** Tab-separated, newest first — matching the standalone indicators page's own clipboard export convention. */
export function buildOverlayValuesText({ overlays }: OverlayExportContext): string {
  const ok = overlays.filter((overlay) => overlay.ok);
  const times = unionTimes(ok).slice().reverse();
  const valueByOverlayAndTime = ok.map(
    (overlay) => new Map(overlay.data.map((point) => [Number(point.time), point.value])),
  );
  const header = ['Timestamp', ...ok.map((overlay) => overlay.label)].join('\t');
  const rows = times.map((time) =>
    [
      isoFromUnixSeconds(time),
      ...valueByOverlayAndTime.map((values) => values.get(time) ?? ''),
    ].join('\t'),
  );
  return [header, ...rows].join('\n');
}
