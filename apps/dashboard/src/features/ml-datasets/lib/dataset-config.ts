import { z } from 'zod';
import { RANGE_PRESETS, type RangePreset } from '@/features/history/lib/resolve-range';
import type { DatasetFormValues } from '@/features/feature-engineering/components/dataset-form';
import type { FeatureSelection } from '@/features/feature-engineering/lib/feature-selection';
import type { SplitRatioValues } from './split-ratios';
import type { TargetSelection } from './target-selection';

/**
 * A fully round-trippable snapshot of everything on this page a
 * researcher configured — market, timeframe, range, feature selections,
 * target selections, and the split ratios — as one plain JSON object.
 *
 * This is a **reproducibility artifact for a person**, not a second
 * dataset-build API: applying an imported config still goes through the
 * exact same "Build ML Dataset" action and the exact same
 * `BuildMLDatasetParams` request every other build on this page sends.
 * Nothing here talks to the backend directly.
 */
export interface DatasetConfig {
  market: string;
  timeframe: string;
  range: RangePreset;
  start: string;
  end: string;
  limit: number;
  features: { feature: string; params: Record<string, string> }[];
  targets: { target: string; params: Record<string, string> }[];
  split: SplitRatioValues;
}

const rangePresetSchema: z.ZodType<RangePreset> = z.enum(RANGE_PRESETS);

const datasetConfigSchema = z.object({
  market: z.string().min(1),
  timeframe: z.string().min(1),
  range: rangePresetSchema.default('all'),
  start: z.string().default(''),
  end: z.string().default(''),
  limit: z.number().int().positive().default(500),
  features: z
    .array(
      z.object({
        feature: z.string().min(1),
        params: z.record(z.string(), z.string()).default({}),
      }),
    )
    .default([]),
  targets: z
    .array(
      z.object({ target: z.string().min(1), params: z.record(z.string(), z.string()).default({}) }),
    )
    .default([]),
  split: z.object({
    train: z.number(),
    validation: z.number(),
    test: z.number(),
  }),
});

export function serializeDatasetConfig(
  form: DatasetFormValues,
  featureSelections: readonly FeatureSelection[],
  targetSelections: readonly TargetSelection[],
  split: SplitRatioValues,
): DatasetConfig {
  return {
    market: form.market,
    timeframe: form.timeframe,
    range: form.range,
    start: form.start,
    end: form.end,
    limit: form.limit,
    features: featureSelections.map((selection) => ({
      feature: selection.feature,
      params: selection.params,
    })),
    targets: targetSelections.map((selection) => ({
      target: selection.target,
      params: selection.params,
    })),
    split,
  };
}

export type ParseDatasetConfigResult =
  { ok: true; config: DatasetConfig } | { ok: false; error: string };

/**
 * Parse and validate a pasted configuration. Never throws — a
 * hand-edited or corrupted paste is an expected input here, not an
 * exceptional one, so the result is a discriminated union the caller
 * renders directly as an inline error rather than a try/catch.
 */
export function parseDatasetConfig(text: string): ParseDatasetConfigResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, error: 'That is not valid JSON.' };
  }

  const result = datasetConfigSchema.safeParse(parsed);
  if (!result.success) {
    const [firstIssue] = result.error.issues;
    const path = firstIssue?.path.join('.') || '(root)';
    return {
      ok: false,
      error: `Invalid configuration at "${path}": ${firstIssue?.message ?? 'unknown error'}`,
    };
  }

  return { ok: true, config: result.data };
}
