import type { Indicator } from '@/types/api/indicators';

/**
 * Whether `indicator` matches a researcher's search query. Matches against
 * name, label, category, every declared alias, and the description — not
 * just label/name/category as the panel's first version did — so a
 * researcher searching "MA" finds the SMA/EMA/WMA family even though none
 * of those names contain the substring "MA" outside their own label, and a
 * researcher who only remembers what an indicator *does* ("momentum",
 * "smooths price") can still find it via the description.
 *
 * An empty/whitespace-only query matches everything, so callers don't need
 * a separate "no filter active" branch.
 */
export function matchesIndicatorSearch(indicator: Indicator, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const haystacks = [
    indicator.name,
    indicator.label,
    indicator.category,
    indicator.description,
    ...(indicator.aliases ?? []),
  ];
  return haystacks.some((value) => value.toLowerCase().includes(needle));
}
