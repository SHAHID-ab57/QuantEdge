import type { ValidationReport } from '@/types/api/dataset-validation';

/** A stable, filesystem-safe name for a downloaded validation report. */
export function reportFilename(report: ValidationReport): string {
  const safe = (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, '-');
  const stamp = report.validated_at.replace(/[^0-9]/g, '').slice(0, 14);
  return `${safe(report.symbol)}-${safe(report.timeframe)}-validation-${stamp}.json`;
}
