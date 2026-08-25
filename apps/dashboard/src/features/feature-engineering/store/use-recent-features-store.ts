'use client';

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/**
 * Session-scoped "recently used features" for the Feature Selector's quick
 * pick list — the same `persist` + `sessionStorage` pattern
 * `use-overlay-store.ts` already established, for the same reason:
 * "recent" means "this session," and `sessionStorage` is the browser
 * primitive that means exactly that (survives a reload, clears when the
 * tab closes) — `localStorage` would silently outlive "this session."
 *
 * Deliberately its own store rather than folded into a page-level
 * `useState`: recency should survive a dataset rebuild, a market change,
 * and a page remount within the same tab, none of which have anything to
 * do with what was recently selected.
 */

const MAX_RECENT = 8;

interface RecentFeaturesState {
  /** Feature names, most-recently-used first, deduplicated. */
  recent: string[];
  recordUsed: (name: string) => void;
  clear: () => void;
}

export const useRecentFeaturesStore = create<RecentFeaturesState>()(
  persist(
    (set) => ({
      recent: [],
      recordUsed: (name) => {
        set((state) => ({
          recent: [name, ...state.recent.filter((existing) => existing !== name)].slice(
            0,
            MAX_RECENT,
          ),
        }));
      },
      clear: () => set({ recent: [] }),
    }),
    {
      name: 'feature-engineering-recent-features',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
