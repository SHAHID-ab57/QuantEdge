/**
 * Searching a flat catalogue entry by name, label, category, aliases, and
 * description.
 *
 * Promoted out of the Indicator Overlay module's own
 * `search-indicators.ts` once the Feature Engineering page needed the
 * identical mechanism over a different catalogue shape — both match a
 * researcher's query against the same five fields, so the fields are the
 * parameter and the mechanism is shared, the same split
 * `group-by-category.ts` already established for grouping.
 */

/** The minimum shape this module needs to search a catalogue entry. */
export interface SearchableEntry {
  name: string;
  label: string;
  category: string;
  description: string;
  aliases?: readonly string[];
}

/**
 * Whether `entry` matches a researcher's search query. Matches name,
 * label, category, every declared alias, and the description — not just
 * label/name/category — so a researcher searching "MA" finds the
 * SMA/EMA/WMA family even though none of those names contain the
 * substring "MA" outside their own label, and a researcher who only
 * remembers what something *does* ("momentum", "smooths price") can still
 * find it via the description.
 *
 * An empty/whitespace-only query matches everything, so callers don't need
 * a separate "no filter active" branch.
 */
export function matchesCatalogSearch(entry: SearchableEntry, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const haystacks = [
    entry.name,
    entry.label,
    entry.category,
    entry.description,
    ...(entry.aliases ?? []),
  ];
  return haystacks.some((value) => value.toLowerCase().includes(needle));
}
