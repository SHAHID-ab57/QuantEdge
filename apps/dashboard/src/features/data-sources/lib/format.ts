/** Matches `StatTile`'s own convention: a value equal to this string renders muted. */
const UNAVAILABLE = 'Unavailable';

/**
 * How many decimal places `formatConnectorValue` shows for a nonzero value
 * of this magnitude — scaled so a genuinely small value (the funding-rate
 * connector's `0.0001`, a fraction per 8h) never silently rounds to a
 * misleading `0`, while a large one (DefiLlama TVL, in the tens of
 * billions) still reads as a clean figure rather than spilling raw
 * `Float`-column noise. `external_data_points.value` is a plain double, so
 * showing *every* decimal it happens to carry would show binary rounding
 * artifacts, not real precision — this picks the smallest number of places
 * that keeps a value truthful for its own scale, not the largest number
 * technically available.
 */
function fractionDigitsFor(absValue: number): number {
  if (absValue >= 1000) {
    return 2;
  }
  if (absValue >= 1) {
    return 4;
  }
  // Below 1: keep at least ~4 significant digits, e.g. 0.0001 -> 7 places,
  // 0.32 -> 4 places, so a small nonzero value is never rounded to zero.
  const magnitude = Math.floor(Math.log10(absValue));
  return Math.min(8, -magnitude + 3);
}

/** A connector's current value — plain, not currency/percentage-formatted:
 * different sources have wildly different units (an index, a rate, a
 * dollar amount), and this page has no per-source knowledge of which.
 * Precision scales with magnitude (see `fractionDigitsFor`) rather than a
 * fixed two decimal places, so a small value is never displayed as `0`. */
export function formatConnectorValue(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  if (value === 0) {
    return '0';
  }
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: fractionDigitsFor(Math.abs(value)),
  }).format(value);
}

/** Full precision, for a tooltip beside a value that `formatConnectorValue`
 * has rounded for display — the exact stored number is always one hover
 * away, never lost. */
export function formatConnectorValueExact(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 20 }).format(value);
}

/** An absolute date + time, for a tooltip beside a relative caption. */
export function formatAbsoluteTimestamp(iso: string | null): string {
  if (!iso) {
    return 'No data yet';
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(
    new Date(iso),
  );
}

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** `"3m"`, `"2h"`, `"5d"` — the coarsest unit that keeps the figure
 * legible, shared by every relative caption on this page so "how long ago"
 * and "how long until" read in the same units. */
function coarseDuration(ms: number): string {
  const abs = Math.abs(ms);
  if (abs < MINUTE) {
    return `${Math.max(1, Math.round(abs / SECOND))}s`;
  }
  if (abs < HOUR) {
    return `${Math.round(abs / MINUTE)}m`;
  }
  if (abs < DAY) {
    return `${Math.round(abs / HOUR)}h`;
  }
  return `${Math.round(abs / DAY)}d`;
}

/** A connector's last-updated caption: *when the value itself is from*
 * ("value as of"), as a relative age rather than a bare date — a value
 * stamped hours ago on today's date used to be indistinguishable from one
 * stamped seconds ago; both read as "22 Sept 2026". The exact instant is
 * still available via `formatAbsoluteTimestamp` as a tooltip. */
export function formatLastUpdated(iso: string | null, now: number = Date.now()): string {
  if (!iso) {
    return 'No data yet';
  }
  const diff = now - new Date(iso).getTime();
  if (diff < 0) {
    return 'just now';
  }
  if (diff < 45 * SECOND) {
    return 'just now';
  }
  return `${coarseDuration(diff)} ago`;
}

// `expected_interval_seconds` is, as its name says, seconds — a distinct
// unit from the millisecond-based SECOND/MINUTE/HOUR/DAY above, which exist
// to divide a `Date.now()` difference. Reusing those here was a real bug
// (86,400 seconds is a day, not 86,400 milliseconds is a day): kept
// deliberately separate rather than "fixed" by converting one input, so a
// future call site can never again pass the wrong unit to the wrong set.
const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE;
const SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR;

/** `86400` -> `"every 1d"`, `28800` -> `"every 8h"` — a connector's own
 * `expected_interval_seconds` as a human phrase, for a caption near its
 * health pill so "why is this stale" has a cadence to check against right
 * there, not just in a tooltip on the word "Stale". */
export function formatInterval(seconds: number): string {
  if (seconds % SECONDS_PER_DAY === 0) {
    return `every ${seconds / SECONDS_PER_DAY}d`;
  }
  if (seconds % SECONDS_PER_HOUR === 0) {
    return `every ${seconds / SECONDS_PER_HOUR}h`;
  }
  if (seconds % SECONDS_PER_MINUTE === 0) {
    return `every ${seconds / SECONDS_PER_MINUTE}m`;
  }
  return `every ${seconds}s`;
}

export interface SyncAttemptStatus {
  /** e.g. `"Fetched 3m ago"` / `"Fetch failed 3m ago"` / `"No sync attempted yet"`. */
  label: string;
  /** Undefined when no attempt has ever been recorded. */
  success?: boolean;
}

/** What the owning scheduler's *last real attempt* to sync this source was
 * — distinct from `latest_timestamp` (the value's own age): an attempt can
 * run, find nothing new, and succeed without moving the value forward at
 * all, and a failed attempt right now can sit beside a value that is still
 * perfectly recent. Surfacing both is what turns a bare "Stale" pill into
 * something explicable without opening the network tab. */
export function formatLastAttempt(
  lastAttemptAt: string | null,
  lastAttemptSuccess: boolean | null,
  now: number = Date.now(),
): SyncAttemptStatus {
  if (!lastAttemptAt) {
    return { label: 'No sync attempted yet' };
  }
  const diff = now - new Date(lastAttemptAt).getTime();
  const age = diff < 45 * SECOND ? 'just now' : `${coarseDuration(diff)} ago`;
  return {
    label: lastAttemptSuccess === false ? `Fetch failed ${age}` : `Fetched ${age}`,
    success: lastAttemptSuccess ?? undefined,
  };
}

export interface NextSyncStatus {
  /** e.g. `"Next sync in 42m"` / `"Next sync overdue by 3h"` / `"Awaiting first sync"`. */
  label: string;
  /** True once the projected time has already passed — the scheduler missed its
   * own tick (a restart, a slow prior run, a database outage), which is itself
   * diagnostic: it means the automation stalled, not that this source's data
   * is fine and simply hasn't been asked for in a while. */
  overdue: boolean;
}

/** `next_sync_at` is a projection (`last_attempt_at` + the owning
 * scheduler's own interval), not a promise — reported as a countdown when
 * still ahead, and as "overdue by X" once passed, which is the one state
 * that actually explains a stuck `stale` pill. */
export function formatNextSync(
  nextSyncAt: string | null,
  now: number = Date.now(),
): NextSyncStatus {
  if (!nextSyncAt) {
    return { label: 'Awaiting first sync', overdue: false };
  }
  const diff = new Date(nextSyncAt).getTime() - now;
  if (diff <= 0) {
    return { label: `Next sync overdue by ${coarseDuration(diff)}`, overdue: true };
  }
  return { label: `Next sync in ${coarseDuration(diff)}`, overdue: false };
}
