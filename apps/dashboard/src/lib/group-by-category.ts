/**
 * Grouping a catalogue into ordered, human-labelled category sections.
 *
 * Promoted out of the Indicator Panel's own `categorize.ts` once the
 * Feature Engineering page needed the identical mechanism over a different
 * taxonomy: both group a flat catalogue under a fixed, curated ordering,
 * fall back gracefully for a category nobody has taxonomized yet, and sort
 * within each group. Only the taxonomy differs, so the taxonomy is the
 * parameter and the mechanism is shared.
 *
 * The fallback is the load-bearing part. Both catalogues are designed to
 * grow — new indicators, new feature generators — and the backend's
 * `category` stays a free-form string on purpose. A category outside the
 * curated list must therefore still render as its own readable section
 * rather than being dropped or crashing the page, which is what lets a new
 * backend category ship with **no frontend change at all**.
 */

/** The minimum shape this module needs to group and sort an entry. */
export interface Categorized {
  category: string;
  label: string;
}

export interface CategoryOrderEntry {
  /** Matched case-insensitively against an entry's `category`. */
  key: string;
  /** Shown as the section heading. */
  label: string;
}

export interface CategoryGroup<T> {
  /** The raw backend category this group came from. */
  key: string;
  label: string;
  items: T[];
}

/** Title-case an uncurated category so it still reads as a section name. */
function fallbackLabel(category: string): string {
  if (!category) {
    return 'Other';
  }
  return category
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => word[0]!.toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Group `items` by category, ordered by `order` and then alphabetically.
 *
 * Curated categories appear first in the order given; anything else follows
 * alphabetically, title-cased. Items within a group are sorted by label so
 * the list is stable regardless of catalogue order.
 */
export function groupByCategory<T extends Categorized>(
  items: readonly T[],
  order: readonly CategoryOrderEntry[],
): CategoryGroup<T>[] {
  const rank = new Map(order.map((entry, index) => [entry.key.toLowerCase(), index]));
  const labels = new Map(order.map((entry) => [entry.key.toLowerCase(), entry.label]));

  const byCategory = new Map<string, T[]>();
  for (const item of items) {
    const existing = byCategory.get(item.category) ?? [];
    existing.push(item);
    byCategory.set(item.category, existing);
  }

  return Array.from(byCategory.entries())
    .sort(([a], [b]) => {
      const rankA = rank.get(a.toLowerCase()) ?? order.length;
      const rankB = rank.get(b.toLowerCase()) ?? order.length;
      return rankA !== rankB ? rankA - rankB : a.localeCompare(b);
    })
    .map(([category, group]) => ({
      key: category,
      label: labels.get(category.toLowerCase()) ?? fallbackLabel(category),
      items: [...group].sort((a, b) => a.label.localeCompare(b.label)),
    }));
}
