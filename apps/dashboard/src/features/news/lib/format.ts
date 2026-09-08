/** An article's published time — date *and* time, unlike
 * `data-sources/lib/format.ts`'s own `formatLastUpdated`: that helper
 * assumes a source publishes at most once a day, but a real article's
 * own `published_at` is meaningfully time-of-day precise. */
export function formatPublishedAt(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  );
}
