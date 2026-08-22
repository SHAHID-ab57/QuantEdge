'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

/**
 * Keeps the selected symbol/timeframe in the URL so a live view is
 * shareable and survives a reload, mirroring the History page's
 * `use-history-url-state.ts`. `router.replace` is used rather than `push`
 * so flipping between markets doesn't bury the previous page under a stack
 * of history entries.
 */
export function useLiveMarketUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const requestedSymbol = searchParams.get('symbol');
  const requestedTimeframe = searchParams.get('timeframe');

  const apply = useCallback(
    (symbol: string, timeframe: string | null) => {
      const next = new URLSearchParams(searchParams.toString());
      next.set('symbol', symbol);
      if (timeframe) {
        next.set('timeframe', timeframe);
      } else {
        next.delete('timeframe');
      }
      const queryString = next.toString();
      if (queryString === searchParams.toString()) {
        return;
      }
      const href = (queryString ? `${pathname}?${queryString}` : pathname) as never;
      router.replace(href, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return { requestedSymbol, requestedTimeframe, apply };
}
