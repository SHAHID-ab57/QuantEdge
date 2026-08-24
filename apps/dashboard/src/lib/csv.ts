/**
 * Minimal CSV helpers shared by every feature that exports tabular data.
 * Promoted out of the History page's export module once the Technical
 * Indicators page needed the identical quoting/escaping rules — two copies
 * of "how do we escape a CSV cell" would inevitably drift.
 */

export function escapeCsv(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

export function csvLine(values: (string | number)[]): string {
  return values.map((value) => escapeCsv(String(value))).join(',');
}

/** Strips anything unsafe for a filename, defaulting to `all` for a null part (e.g. an unset date range). */
export function sanitizeFilenamePart(value: string | null): string {
  return value ? value.replace(/[^a-zA-Z0-9_-]/g, '-') : 'all';
}
