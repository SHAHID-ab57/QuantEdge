'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';
import { HISTORY_LIMIT_OPTIONS } from '../components/history-form';
import { isRangePreset, resolveRange, type RangePreset } from '../lib/resolve-range';
import {
  CANDLE_SORT_COLUMNS,
  type CandleSortColumn,
  type CandleSortDirection,
  type HistoryQuery,
} from './use-history-data';

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

export interface HistoryUrlState {
  query: HistoryQuery;
  page: number;
}

function isoDateOrNull(value: string | null): string | null {
  if (!value || !ISO_DATE_PATTERN.test(value)) {
    return null;
  }
  return value;
}

/** Build the initial query from URL search params, or null when incomplete. */
export function queryFromSearchParams(searchParams: URLSearchParams): HistoryUrlState | null {
  const market = searchParams.get('market');
  const timeframe = searchParams.get('timeframe');
  if (!market || !timeframe) {
    return null;
  }
  const rangeParam = searchParams.get('range');
  const range: RangePreset = isRangePreset(rangeParam) ? rangeParam : 'all';
  const limitValue = Number(searchParams.get('limit'));
  const limit = (HISTORY_LIMIT_OPTIONS as readonly number[]).includes(limitValue)
    ? limitValue
    : HISTORY_LIMIT_OPTIONS[0]!;
  const sortValue = searchParams.get('sort');
  const sort: CandleSortColumn = (CANDLE_SORT_COLUMNS as readonly string[]).includes(
    sortValue ?? '',
  )
    ? (sortValue as CandleSortColumn)
    : 'open_time';
  const dir: CandleSortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';
  const pageValue = Number(searchParams.get('page'));
  const page = Number.isInteger(pageValue) && pageValue > 0 ? pageValue : 1;

  let start: string | null = null;
  let end: string | null = null;
  if (range === 'custom') {
    start = isoDateOrNull(searchParams.get('start'));
    end = isoDateOrNull(searchParams.get('end'));
    if (!start || !end) {
      return null;
    }
  } else {
    const resolved = resolveRange(range);
    start = resolved.start;
    end = resolved.end;
  }
  return {
    query: { symbol: market, timeframe, start, end, limit, sort, dir },
    page,
  };
}

export function useHistoryUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const apply = useCallback(
    (query: HistoryQuery, page: number) => {
      const next = new URLSearchParams(searchParams.toString());
      next.set('market', query.symbol);
      next.set('timeframe', query.timeframe);
      if (query.start && query.end) {
        next.set('start', query.start);
        next.set('end', query.end);
        next.set('range', 'custom');
      } else {
        next.delete('start');
        next.delete('end');
        next.delete('range');
      }
      next.set('limit', String(query.limit));
      next.set('sort', query.sort);
      next.set('dir', query.dir);
      if (page > 1) {
        next.set('page', String(page));
      } else {
        next.delete('page');
      }
      const queryString = next.toString();
      const href = (queryString ? `${pathname}?${queryString}` : pathname) as never;
      router.replace(href, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return { apply };
}
