import { MODEL_KINDS, type ModelKind } from '@/types/api/training';

/**
 * A `BenchmarkCandidate.model_kind` is a plain string on the wire — it can
 * be `"unknown"` when the job's own `model_type` is no longer a registered
 * adapter (`app/services/evaluation.py`). Narrows to the three literals
 * `EvaluationSummary` actually understands, so an unrecognized value falls
 * back to that component's own generic metrics list rather than being
 * force-cast.
 */
export function toModelKind(value: string): ModelKind | undefined {
  return (MODEL_KINDS as readonly string[]).includes(value) ? (value as ModelKind) : undefined;
}
