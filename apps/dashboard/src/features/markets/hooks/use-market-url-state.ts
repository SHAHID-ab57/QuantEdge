'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

export const MARKET_TYPE_OPTIONS = ['spot', 'perpetual', 'expiry'] as const;
export const DEFAULT_PAGE_SIZE = 10;
export const PAGE_SIZE_OPTIONS = [10, 25, 50];

export type SortKey = 'symbol' | 'exchange' | 'base_asset' | 'quote_asset' | 'market_type';
export type SortDir = 'asc' | 'desc';

export const SORT_KEYS: SortKey[] = [
  'symbol',
  'exchange',
  'base_asset',
  'quote_asset',
  'market_type',
];

export interface MarketUrlState {
  q: string;
  type: string;
  status: string;
  exchange: string;
  sort: SortKey;
  dir: SortDir;
  page: number;
  size: number;
  hasFilters: boolean;
}

const SEARCH_DEBOUNCE_MS = 300;

export function useMarketUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [q, setQ] = useState(() => searchParams.get('q') ?? '');
  const [type, setType] = useState(() => searchParams.get('type') ?? '');
  const [status, setStatus] = useState(() => searchParams.get('status') ?? '');
  const [exchange, setExchange] = useState(() => searchParams.get('exchange') ?? '');
  const [sort, setSort] = useState<SortKey>(() => {
    const value = searchParams.get('sort');
    return SORT_KEYS.includes(value as SortKey) ? (value as SortKey) : 'symbol';
  });
  const [dir, setDir] = useState<SortDir>(() =>
    searchParams.get('dir') === 'desc' ? 'desc' : 'asc',
  );
  const [page, setPage] = useState(() => {
    const value = Number(searchParams.get('page'));
    return Number.isInteger(value) && value > 0 ? value : 1;
  });
  const [size, setSize] = useState(() => {
    const value = Number(searchParams.get('size'));
    return PAGE_SIZE_OPTIONS.includes(value) ? value : DEFAULT_PAGE_SIZE;
  });

  const [qDebounced, setQDebounced] = useState(q);
  useEffect(() => {
    const timer = setTimeout(() => setQDebounced(q), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [q]);

  const apply = useCallback(
    (patch: Partial<Omit<MarketUrlState, 'hasFilters'>>) => {
      const next = new URLSearchParams(searchParams.toString());
      const setParam = (key: string, value: string | number | undefined) => {
        if (value === undefined || value === '' || value === 1) {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
      };
      if ('q' in patch) {
        setParam('q', patch.q);
      }
      if ('type' in patch) {
        setParam('type', patch.type);
        next.delete('page');
      }
      if ('status' in patch) {
        setParam('status', patch.status);
        next.delete('page');
      }
      if ('exchange' in patch) {
        setParam('exchange', patch.exchange);
        next.delete('page');
      }
      if ('sort' in patch) {
        setParam('sort', patch.sort);
        next.delete('page');
      }
      if ('dir' in patch) {
        setParam('dir', patch.dir);
      }
      if ('page' in patch) {
        setParam('page', patch.page);
      }
      if ('size' in patch) {
        setParam('size', patch.size);
        next.delete('page');
      }
      const query = next.toString();
      const href = (query ? `${pathname}?${query}` : pathname) as never;
      router.replace(href, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    if (qDebounced !== (searchParams.get('q') ?? '')) {
      apply({ q: qDebounced });
    }
  }, [apply, qDebounced, searchParams]);

  const setSearch = useCallback((value: string) => {
    setQ(value);
    setPage(1);
  }, []);

  const setFilter = useCallback((key: 'type' | 'status' | 'exchange', value: string) => {
    if (key === 'type') {
      setType(value);
    } else if (key === 'status') {
      setStatus(value);
    } else {
      setExchange(value);
    }
    setPage(1);
  }, []);

  const toggleSort = useCallback(
    (key: SortKey) => {
      if (key === sort) {
        setDir((current) => (current === 'asc' ? 'desc' : 'asc'));
        apply({ dir: dir === 'asc' ? 'desc' : 'asc' });
      } else {
        setSort(key);
        apply({ sort: key, dir: 'asc' });
      }
    },
    [apply, dir, sort],
  );

  const changePage = useCallback(
    (value: number) => {
      setPage(value);
      apply({ page: value });
    },
    [apply],
  );

  const changeSize = useCallback(
    (value: number) => {
      setSize(value);
      setPage(1);
      apply({ size: value });
    },
    [apply],
  );

  const clearFilters = useCallback(() => {
    setQ('');
    setType('');
    setStatus('');
    setExchange('');
    setPage(1);
    apply({ q: '', type: '', status: '', exchange: '' });
  }, [apply]);

  const hasFilters = Boolean(qDebounced || type || status || exchange);

  const state = useMemo<MarketUrlState>(
    () => ({ q, type, status, exchange, sort, dir, page, size, hasFilters }),
    [q, type, status, exchange, sort, dir, page, size, hasFilters],
  );

  return {
    state,
    setSearch,
    setFilter,
    toggleSort,
    changePage,
    changeSize,
    clearFilters,
  };
}
