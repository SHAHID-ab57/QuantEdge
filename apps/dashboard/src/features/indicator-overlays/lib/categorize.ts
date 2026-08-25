import { groupByCategory, type CategoryOrderEntry } from '@/lib/group-by-category';
import type { Indicator } from '@/types/api/indicators';

/**
 * The canonical category taxonomy the Indicator Panel groups by. Any
 * indicator whose backend `category` doesn't match one of these keys
 * (case-insensitively) is title-cased into its own group rather than being
 * dropped — a future indicator with a category nobody has taxonomized yet
 * must still appear somewhere, not vanish from the panel.
 *
 * This list is deliberately UI-only: the backend's `category` remains a
 * free-form string (see `ARCHITECTURE.md` § "Technical Indicator Engine"),
 * so adding a new indicator with a brand-new category needs no schema
 * change here.
 *
 * The grouping *mechanism* lives in `@/lib/group-by-category`, shared with
 * the Feature Engineering catalogue, which groups a different taxonomy the
 * same way. Only the taxonomy below is specific to indicators.
 */
const CATEGORY_ORDER: readonly CategoryOrderEntry[] = [
  { key: 'trend', label: 'Trend' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'volatility', label: 'Volatility' },
  { key: 'volume', label: 'Volume' },
  { key: 'oscillators', label: 'Oscillators' },
  { key: 'statistical', label: 'Statistical' },
];

export interface IndicatorCategoryGroup {
  key: string;
  label: string;
  indicators: Indicator[];
}

/**
 * Groups indicators by category in a fixed, researcher-friendly order
 * (Trend, Momentum, Volatility, Volume, Oscillators, Statistical, then any
 * uncurated categories alphabetically) — never in raw catalogue order,
 * which would jumble unrelated indicator families together as the
 * catalogue grows past a handful of entries.
 */
export function groupIndicatorsByCategory(
  indicators: readonly Indicator[],
): IndicatorCategoryGroup[] {
  return groupByCategory(indicators, CATEGORY_ORDER).map((group) => ({
    key: group.key,
    label: group.label,
    indicators: group.items,
  }));
}
