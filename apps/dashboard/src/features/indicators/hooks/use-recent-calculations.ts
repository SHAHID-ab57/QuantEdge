'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  readRecentCalculations,
  withRecentCalculation,
  writeRecentCalculations,
  type RecentCalculation,
} from '../lib/recent-calculations';

/**
 * Per-browser convenience state: the last several calculations run on this
 * page, persisted to `localStorage` so they survive a reload but never
 * leave this viewer's browser. Read lazily on mount only (not on every
 * tab's storage event) — this is a single-tab research workflow, not
 * state that needs cross-tab synchronization.
 */
export function useRecentCalculations() {
  const [entries, setEntries] = useState<RecentCalculation[]>([]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setEntries(readRecentCalculations(window.localStorage));
    }
  }, []);

  const record = useCallback((entry: RecentCalculation) => {
    setEntries((previous) => {
      const next = withRecentCalculation(previous, entry);
      if (typeof window !== 'undefined') {
        writeRecentCalculations(window.localStorage, next);
      }
      return next;
    });
  }, []);

  return { entries, record };
}
