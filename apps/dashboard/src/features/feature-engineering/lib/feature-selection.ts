import { groupByCategory, type CategoryOrderEntry } from '@/lib/group-by-category';
import type { Feature, FeatureCell } from '@/types/api/features';
import type { FeatureRequestBody } from '@/lib/api/features';

/**
 * Pure helpers for the Feature Engineering page's selection state and cell
 * rendering. Kept free of React and of the DOM so the rules that decide
 * *what gets requested* are testable without mounting anything — the same
 * split the indicator and overlay modules use.
 */

/**
 * The feature catalogue's taxonomy, ordered for a researcher building a
 * dataset: raw inputs first, then the derived families. As with the
 * indicator taxonomy this is UI-only — a generator with a brand-new
 * backend category still renders in its own title-cased group.
 */
const CATEGORY_ORDER: readonly CategoryOrderEntry[] = [
  { key: 'raw', label: 'Raw Market Data' },
  { key: 'price_action', label: 'Price Action' },
  { key: 'trend', label: 'Trend' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'volatility', label: 'Volatility' },
  { key: 'volume', label: 'Volume' },
  { key: 'statistical', label: 'Statistical' },
];

export interface FeatureCategoryGroup {
  key: string;
  label: string;
  features: Feature[];
}

/** Group the catalogue into ordered, labelled sections for the selector. */
export function groupFeaturesByCategory(features: readonly Feature[]): FeatureCategoryGroup[] {
  return groupByCategory(features, CATEGORY_ORDER).map((group) => ({
    key: group.key,
    label: group.label,
    features: group.items,
  }));
}

/** One feature a researcher has selected, with the parameter values they set. */
export interface FeatureSelection {
  feature: string;
  params: Record<string, string>;
}

/**
 * Seed a selection's parameters from the generator's own published
 * defaults, so a newly-ticked feature is immediately valid without the
 * researcher having to fill anything in.
 *
 * Reads the defaults out of the catalogue rather than hardcoding them,
 * which is what lets a new backend generator work here with no frontend
 * change.
 */
export function defaultParamsFor(feature: Feature): Record<string, string> {
  const params: Record<string, string> = {};
  for (const spec of feature.parameters) {
    if (spec.default !== null && spec.default !== undefined) {
      params[spec.name] = String(spec.default);
    }
  }
  return params;
}

/** Toggle a feature in or out of the selection, preserving the order of the rest. */
export function toggleSelection(
  selections: readonly FeatureSelection[],
  feature: Feature,
): FeatureSelection[] {
  const existing = selections.find((selection) => selection.feature === feature.name);
  if (existing) {
    return selections.filter((selection) => selection.feature !== feature.name);
  }
  return [...selections, { feature: feature.name, params: defaultParamsFor(feature) }];
}

/** Replace one selection's parameters, leaving every other selection untouched. */
export function updateSelectionParams(
  selections: readonly FeatureSelection[],
  feature: string,
  params: Record<string, string>,
): FeatureSelection[] {
  return selections.map((selection) =>
    selection.feature === feature ? { ...selection, params } : selection,
  );
}

export function isSelected(selections: readonly FeatureSelection[], feature: string): boolean {
  return selections.some((selection) => selection.feature === feature);
}

/** Map the page's selection state onto the API's request shape. */
export function toRequestBodies(selections: readonly FeatureSelection[]): FeatureRequestBody[] {
  return selections.map((selection) => ({
    feature: selection.feature,
    params: selection.params,
  }));
}

/**
 * Render one dataset cell for display.
 *
 * Floats are shown to at most six significant digits — enough to read a
 * price or a normalized fraction without the noise of full float
 * precision — while integers, booleans, and categoricals are shown
 * verbatim. `null` renders as an em dash rather than an empty cell so a
 * missing value is visibly missing rather than looking like a rendering
 * gap. This is display-only: exports always carry the raw values.
 */
export function formatCell(value: FeatureCell): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (typeof value === 'number') {
    if (Number.isInteger(value)) {
      return String(value);
    }
    return Number(value.toPrecision(6)).toString();
  }
  return value;
}

/** A short, readable summary of the parameters a selection will run with. */
export function paramSummary(selection: FeatureSelection): string {
  const pairs = Object.entries(selection.params).map(([key, value]) => `${key}=${value}`);
  return pairs.length > 0 ? pairs.join(', ') : 'no parameters';
}
