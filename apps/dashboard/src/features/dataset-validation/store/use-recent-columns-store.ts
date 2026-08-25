'use client';

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/**
 * Session-scoped "recently used required columns" for the Required
 * Columns selector's quick-pick row — the identical `persist` +
 * `sessionStorage` pattern `use-recent-features-store.ts` already
 * established, applied to column names instead of feature names, for the
 * same reason: "recent" means "this session," not indefinite persistence.
 */

const MAX_RECENT = 8;

interface RecentColumnsState {
  /** Column names, most-recently-used first, deduplicated. */
  recent: string[];
  recordUsed: (name: string) => void;
  clear: () => void;
}

export const useRecentColumnsStore = create<RecentColumnsState>()(
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
      name: 'dataset-validation-recent-columns',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
