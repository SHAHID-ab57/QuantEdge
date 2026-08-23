'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

/**
 * Keeps the selected symbol in the URL (`?symbol=`) for a page that has no
 * other query-string state — originally built for the Order Book viewer,
 * promoted here once the Live Trade Analytics dashboard needed the exact
 * same behavior. Symbol-only, unlike the Live Market Dashboard's own
 * `use-live-market-url-state.ts` (which also tracks `timeframe`) — reusing
 * that one instead would mean writing a meaningless `timeframe` param into
 * a URL for a page that has no timeframe concept.
 */
export function useSymbolUrlState() {
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
