/** Matches `StatTile`'s own convention: a value equal to this string renders muted. */
const UNAVAILABLE = 'Unavailable';

/** A connector's current value — plain, not currency/percentage-formatted:
 * different sources will have wildly different units (an index, a rate, a
 * dollar amount), and this page has no per-source knowledge of which. */
export function formatConnectorValue(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

/** A connector's last-updated caption. Fear & Greed (and every source
 * planned for this milestone) publishes at most once a day, so an
 * absolute date reads better here than a live-ticking "x minutes ago". */
export function formatLastUpdated(iso: string | null): string {
  if (!iso) {
    return 'No data yet';
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(iso));
}
