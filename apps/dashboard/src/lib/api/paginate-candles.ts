import { fetchCandlePage } from './market';
import type { Candle, CandlePage } from '@/types/api/market';

/** A hard ceiling on how many pages any single caller will fetch, regardless of what the backend reports as `total`. */
const DEFAULT_MAX_PAGES = 250;

export interface PaginateCandlesQuery {
  symbol: string;
  timeframe: string;
  start?: string | null;
  end?: string | null;
  limit: number;
  sort?: string;
  dir?: string;
}

export interface PaginateCandlesResult {
  candles: Candle[];
  /** The first page's response — carries `pagination.total` and any other page-level metadata. */
  firstPage: CandlePage;
  /** `true` if `maxPages` was hit before the backend ran out of candles to return. */
  truncated: boolean;
}

/**
 * Fetches every candle matching `query` by walking `GET .../candles`'s
 * offset-based pagination (`services/api/app/api/v1/endpoints/market_data.py`,
 * capped server-side at `candles_max_limit` per page, 1000 by default) until
 * the backend reports no more, or until `maxPages` is hit — whichever comes
 * first. Originally written for the History page's CSV/JSON export
 * (fetching a whole query's worth of candles page-by-page) and promoted
 * here once the Replay engine needed the identical behavior: loading a full
 * session's candles up front so replay can step through them without any
 * further network round-trip. `onProgress`, if given, is called after every
 * page with the running total fetched and the backend's reported total.
 */
export async function fetchAllCandles(
  query: PaginateCandlesQuery,
  onProgress?: (fetched: number, total: number) => void,
  maxPages: number = DEFAULT_MAX_PAGES,
): Promise<PaginateCandlesResult> {
  const candles: Candle[] = [];
  let firstPage: CandlePage | null = null;
  let offset = 0;
  let total = Infinity;
  let pagesFetched = 0;
  let truncated = false;

  while (offset < total) {
    if (pagesFetched >= maxPages) {
      truncated = true;
      break;
    }
    const page = await fetchCandlePage(query.symbol, query.timeframe, {
      limit: query.limit,
      offset,
      start: query.start ?? undefined,
      end: query.end ?? undefined,
      sort: query.sort,
      dir: query.dir,
    });
    firstPage ??= page;
    pagesFetched += 1;
    candles.push(...page.items);
    total = page.pagination.total;
    offset += page.items.length;
    onProgress?.(candles.length, total);
    if (page.items.length === 0) {
      break;
    }
  }

  return { candles, firstPage: firstPage as CandlePage, truncated };
}
