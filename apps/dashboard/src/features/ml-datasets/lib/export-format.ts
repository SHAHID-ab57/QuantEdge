/**
 * The export formats this builder supports, as data rather than as
 * hardcoded buttons — adding a future format (e.g. Parquet) means adding
 * one entry here, not redesigning `MLDatasetExport`/`ExportSummaryDialog`/
 * `MLDatasetMetadataPanel`, all three of which read this list rather than
 * naming "csv"/"json" individually.
 */
export interface ExportFormatOption {
  format: 'csv' | 'json';
  label: string;
  /** Rough bytes-per-cell used only for the pre-export size estimate — see `estimateExportBytes`. */
  bytesPerCellEstimate: number;
}

export const EXPORT_FORMAT_OPTIONS: readonly ExportFormatOption[] = [
  { format: 'csv', label: 'CSV', bytesPerCellEstimate: 8 },
  { format: 'json', label: 'JSON', bytesPerCellEstimate: 14 },
];

/**
 * A rough, explicitly-labeled-as-approximate export size, for the Export
 * Summary dialog. Real cell sizes vary a lot (a short int vs. a long
 * float vs. a `null`), so this is a heuristic for "is this roughly a
 * megabyte or a gigabyte," not a byte-accurate prediction — the dialog
 * that renders it says "approximate" rather than implying precision this
 * estimate cannot deliver.
 */
export function estimateExportBytes(
  rowCount: number,
  columnCount: number,
  format: ExportFormatOption['format'],
): number {
  const option = EXPORT_FORMAT_OPTIONS.find((entry) => entry.format === format);
  const bytesPerCell = option?.bytesPerCellEstimate ?? 10;
  // +1 column for the split label every export row also carries.
  return rowCount * (columnCount + 1) * bytesPerCell;
}

const UNITS = ['B', 'KB', 'MB', 'GB'] as const;

export function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < UNITS.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const unit = UNITS[unitIndex] ?? 'B';
  // Round to one decimal place, then drop a trailing ".0" — "2 KB", not "2.0 KB".
  return `${Number(value.toFixed(1))} ${unit}`;
}
