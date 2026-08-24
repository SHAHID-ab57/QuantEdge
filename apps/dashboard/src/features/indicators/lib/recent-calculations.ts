/**
 * Pure persistence helpers for the "recent calculations" list, kept
 * separate from the React hook that uses them so the localStorage
 * read/write logic and the capped-list behavior can be tested without
 * rendering anything.
 *
 * This is per-viewer convenience state (like a remembered tab or filter),
 * not data that must be shared or durable — the same category this
 * codebase's Zustand store is reserved for (sidebar open/collapsed), which
 * is why this stays a plain localStorage-backed hook rather than expanding
 * that store's scope.
 */

export interface RecentCalculation {
  symbol: string;
  indicator: string;
  indicatorLabel: string;
  timeframe: string;
  params: Record<string, string>;
  /** Epoch milliseconds. */
  timestamp: number;
}

export const RECENT_CALCULATIONS_KEY = 'indicators.recentCalculations';
export const MAX_RECENT_CALCULATIONS = 10;

function sameConfiguration(a: RecentCalculation, b: RecentCalculation): boolean {
  return (
    a.symbol === b.symbol &&
    a.indicator === b.indicator &&
    a.timeframe === b.timeframe &&
    JSON.stringify(a.params) === JSON.stringify(b.params)
  );
}

/**
 * Prepends a new entry, de-duplicating an identical configuration (the
 * researcher re-running the same thing moves it back to the top instead
 * of appearing twice) and capping the list length.
 */
export function withRecentCalculation(
  existing: RecentCalculation[],
  entry: RecentCalculation,
): RecentCalculation[] {
  const withoutDuplicate = existing.filter((candidate) => !sameConfiguration(candidate, entry));
  return [entry, ...withoutDuplicate].slice(0, MAX_RECENT_CALCULATIONS);
}

/** Reads the stored list, tolerating a missing, cleared, or corrupted value. */
export function readRecentCalculations(storage: Storage): RecentCalculation[] {
  try {
    const raw = storage.getItem(RECENT_CALCULATIONS_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as RecentCalculation[]) : [];
  } catch {
    return [];
  }
}

/** Writes the list, tolerating a storage that throws (private browsing, quota, disabled site data). */
export function writeRecentCalculations(storage: Storage, entries: RecentCalculation[]): void {
  try {
    storage.setItem(RECENT_CALCULATIONS_KEY, JSON.stringify(entries));
  } catch {
    // Best-effort convenience state — losing it is not worth surfacing an error for.
  }
}
