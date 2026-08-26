import type { TargetDTO } from '@/types/api/ml-datasets';
import type { TargetRequestBody } from '@/lib/api/ml-datasets';

/**
 * Pure helpers for the ML Dataset Builder's target-selection state — the
 * target-side counterpart to `feature-engineering/lib/feature-selection.ts`.
 * Kept free of React so the rules that decide *what gets requested* are
 * testable without mounting anything.
 */

/** One prediction target a researcher has selected, with the parameter values they set. */
export interface TargetSelection {
  target: string;
  params: Record<string, string>;
}

/**
 * Seed a selection's parameters from the generator's own published
 * defaults (typically just `horizon`), so a newly-ticked target is
 * immediately valid without the researcher filling anything in.
 */
export function defaultParamsForTarget(target: TargetDTO): Record<string, string> {
  const params: Record<string, string> = {};
  for (const spec of target.parameters) {
    if (spec.default !== null && spec.default !== undefined) {
      params[spec.name] = String(spec.default);
    }
  }
  return params;
}

/** Toggle a target in or out of the selection, preserving the order of the rest. */
export function toggleTargetSelection(
  selections: readonly TargetSelection[],
  target: TargetDTO,
): TargetSelection[] {
  const existing = selections.find((selection) => selection.target === target.name);
  if (existing) {
    return selections.filter((selection) => selection.target !== target.name);
  }
  return [...selections, { target: target.name, params: defaultParamsForTarget(target) }];
}

/** Replace one selection's parameters, leaving every other selection untouched. */
export function updateTargetSelectionParams(
  selections: readonly TargetSelection[],
  target: string,
  params: Record<string, string>,
): TargetSelection[] {
  return selections.map((selection) =>
    selection.target === target ? { ...selection, params } : selection,
  );
}

export function isTargetSelected(selections: readonly TargetSelection[], target: string): boolean {
  return selections.some((selection) => selection.target === target);
}

/** Map the page's selection state onto the API's request shape. */
export function toTargetRequestBodies(selections: readonly TargetSelection[]): TargetRequestBody[] {
  return selections.map((selection) => ({
    target: selection.target,
    params: selection.params,
  }));
}

/** A short, readable summary of the parameters a selection will run with. */
export function targetParamSummary(selection: TargetSelection): string {
  const pairs = Object.entries(selection.params).map(([key, value]) => `${key}=${value}`);
  return pairs.length > 0 ? pairs.join(', ') : 'default horizon';
}
