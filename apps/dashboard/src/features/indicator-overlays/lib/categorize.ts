import type { Indicator } from '@/types/api/indicators';

/**
 * The canonical category taxonomy the Indicator Panel groups by. Any
 * indicator whose backend `category` doesn't match one of these keys
 * (case-insensitively) falls into "Other" rather than being dropped — a
 * future indicator with a category nobody has taxonomized yet must still
 * appear somewhere, not vanish from the panel.
 *
 * This list is deliberately UI-only: the backend's `category` remains a
 * free-form string (see `ARCHITECTURE.md` § "Technical Indicator Engine"),
 * so adding a new indicator with a brand-new category needs no schema
 * change here — it simply lands in "Other" until this list is extended.
 */
const CATEGORY_ORDER = [
  { key: 'trend', label: 'Trend' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'volatility', label: 'Volatility' },
  { key: 'volume', label: 'Volume' },
  { key: 'oscillators', label: 'Oscillators' },
  { key: 'statistical', label: 'Statistical' },
] as const;

const OTHER_LABEL = 'Other';

export interface IndicatorCategoryGroup {
  key: string;
  label: string;
  indicators: Indicator[];
}

function categoryLabel(category: string): string {
  const known = CATEGORY_ORDER.find((entry) => entry.key === category.toLowerCase());
  if (known) {
    return known.label;
  }
  // An uncurated category is shown title-cased rather than raw/lowercase,
  // so a future indicator's category still reads as a proper group name.
  return category.length > 0 ? category[0]!.toUpperCase() + category.slice(1) : OTHER_LABEL;
}

function categoryRank(category: string): number {
  const index = CATEGORY_ORDER.findIndex((entry) => entry.key === category.toLowerCase());
  return index === -1 ? CATEGORY_ORDER.length : index;
}

/**
 * Groups indicators by category in a fixed, researcher-friendly order
 * (Trend, Momentum, Volatility, Volume, Oscillators, Statistical, then any
 * uncurated categories alphabetically) — never grouped in raw catalogue
 * order, which would jumble unrelated indicator families together as the
 * catalogue grows past a handful of entries.
 */
export function groupIndicatorsByCategory(
  indicators: readonly Indicator[],
): IndicatorCategoryGroup[] {
  const byCategory = new Map<string, Indicator[]>();
  for (const indicator of indicators) {
    const list = byCategory.get(indicator.category) ?? [];
    list.push(indicator);
    byCategory.set(indicator.category, list);
  }

  return Array.from(byCategory.entries())
    .sort(([a], [b]) => {
      const rankDiff = categoryRank(a) - categoryRank(b);
      return rankDiff !== 0 ? rankDiff : a.localeCompare(b);
    })
    .map(([category, list]) => ({
      key: category,
      label: categoryLabel(category),
      indicators: [...list].sort((a, b) => a.label.localeCompare(b.label)),
    }));
}
