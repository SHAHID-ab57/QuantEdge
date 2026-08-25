import type { Indicator } from '@/types/api/indicators';
import { matchesCatalogSearch } from '@/lib/search-catalog';

/**
 * Whether `indicator` matches a researcher's search query — see
 * `matchesCatalogSearch` (`@/lib/search-catalog`) for the shared matching
 * rule this delegates to; only the catalogue type is specific to
 * indicators.
 */
export function matchesIndicatorSearch(indicator: Indicator, query: string): boolean {
  return matchesCatalogSearch(indicator, query);
}
