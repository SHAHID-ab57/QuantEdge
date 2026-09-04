'use client';

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/**
 * The current paper trading account id, persisted to `localStorage` —
 * the same "deliberately durable, not session-scoped" exception
 * `use-favorite-features-store.ts` already established. Nothing on this
 * platform authenticates a user, so there is no server-side identity to
 * key a "my account" concept off of; remembering the id locally is what
 * lets a trader open the page tomorrow and see the same account rather
 * than a blank slate every visit. `GET /paper-trading/accounts` (Account
 * History, on this page) is the recovery path if this is ever cleared.
 */

interface PaperTradingAccountState {
  accountId: string | null;
  setAccountId: (accountId: string | null) => void;
}

export const usePaperTradingAccountStore = create<PaperTradingAccountState>()(
  persist(
    (set) => ({
      accountId: null,
      setAccountId: (accountId) => set({ accountId }),
    }),
    {
      name: 'paper-trading-current-account',
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
