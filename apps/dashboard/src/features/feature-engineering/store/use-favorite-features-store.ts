'use client';

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/**
 * Long-lived "favorite features," deliberately persisted to `localStorage`
 * rather than `sessionStorage` — the one place this platform's session-
 * scoped `persist` convention (`use-recent-features-store.ts`,
 * `use-overlay-store.ts`) is intentionally *not* followed. "Recent" means
 * "this session" by definition; a favorite is the opposite — a deliberate,
 * durable marking a researcher wants to survive closing the tab and coming
 * back tomorrow, the same way a starred email or a bookmarked page would.
 */

interface FavoriteFeaturesState {
  /** Feature names a researcher has starred, unordered. */
  favorites: string[];
  toggle: (name: string) => void;
  isFavorite: (name: string) => boolean;
  clear: () => void;
}

export const useFavoriteFeaturesStore = create<FavoriteFeaturesState>()(
  persist(
    (set, get) => ({
      favorites: [],
      toggle: (name) => {
        set((state) =>
          state.favorites.includes(name)
            ? { favorites: state.favorites.filter((existing) => existing !== name) }
            : { favorites: [...state.favorites, name] },
        );
      },
      isFavorite: (name) => get().favorites.includes(name),
      clear: () => set({ favorites: [] }),
    }),
    {
      name: 'feature-engineering-favorite-features',
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
