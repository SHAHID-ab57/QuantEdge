'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

/**
 * Keeps the selected symbol in the URL (`?symbol=`), mirroring the Live
 * Market Dashboard's `use-live-market-url-state.ts` — but symbol-only,
 * since an order book has no timeframe concept. Kept as its own small hook
 * rather than reusing the live-market one directly: reusing it would mean
 * writing a meaningless `timeframe` param into this page's URL.
 */
export function useOrderBookUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const requestedSymbol = searchParams.get('symbol');

  const apply = useCallback(
    (symbol: string) => {
      const next = new URLSearchParams(searchParams.toString());
      next.set('symbol', symbol);
      const queryString = next.toString();
      if (queryString === searchParams.toString()) {
        return;
      }
      const href = (queryString ? `${pathname}?${queryString}` : pathname) as never;
      router.replace(href, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return { requestedSymbol, apply };
}
