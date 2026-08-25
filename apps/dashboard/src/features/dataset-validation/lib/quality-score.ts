import type { ValidationSummary } from '@/types/api/dataset-validation';

/**
 * A deliberately simple, frontend-only heuristic for "how healthy did this
 * dataset look," derived entirely from the report's own `summary` — never
 * a backend field, since the validation engine's contract is the pass/fail
 * verdict plus the issue list, not a single blended number (see
 * `ARCHITECTURE.md` § "Dataset Validation & Quality Engine": severity is
 * intentionally three-tier, not a score). This score exists purely as a UI
 * triage aid for scanning many datasets quickly; it is not a statistical
 * or scientific measure, and `qualityScoreLabel`/the summary card's own
 * tooltip say so explicitly rather than implying more rigor than exists.
 *
 * Errors cost three times what warnings do, reflecting that only errors
 * fail the gate at all (`ValidationReport.passed`) — the weighting isn't
 * arbitrary, it mirrors the same asymmetry the engine's own severity model
 * already encodes.
 */
const ERROR_PENALTY = 15;
const WARNING_PENALTY = 5;

export function computeQualityScore(summary: ValidationSummary): number {
  const penalty = summary.errors * ERROR_PENALTY + summary.warnings * WARNING_PENALTY;
  return Math.max(0, Math.min(100, Math.round(100 - penalty)));
}

export type QualityBand = 'excellent' | 'good' | 'fair' | 'poor';

/** A coarse label for the score, for a color/tone decision — never shown as the only explanation. */
export function qualityBand(score: number): QualityBand {
  if (score >= 90) return 'excellent';
  if (score >= 70) return 'good';
  if (score >= 40) return 'fair';
  return 'poor';
}
