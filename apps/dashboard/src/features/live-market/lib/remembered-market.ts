/**
 * Persistence for the user's last Live Market selection.
 *
 * The URL is the authoritative, shareable copy (see
 * `use-live-market-url-state.ts`); local storage is the cross-visit
 * fallback for when the page is opened without any search params. Every
 * access is guarded because `localStorage` throws in private-mode browsers
 * and is simply absent during server rendering — a research dashboard must
 * not fail to load because a storage quota was hit.
 */

const SYMBOL_KEY = 'live-market:symbol';
const TIMEFRAME_KEY = 'live-market:timeframe';

export interface RememberedMarket {
  symbol: string | null;
  timeframe: string | null;
}

function readKey(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeKey(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage is full, disabled, or blocked — the URL still carries the
    // selection for this session, so there is nothing to recover from.
  }
}

export function readRememberedMarket(): RememberedMarket {
  if (typeof window === 'undefined') {
    return { symbol: null, timeframe: null };
  }
  return { symbol: readKey(SYMBOL_KEY), timeframe: readKey(TIMEFRAME_KEY) };
}

export function rememberMarket(symbol: string, timeframe: string | null): void {
  if (typeof window === 'undefined') {
    return;
  }
  writeKey(SYMBOL_KEY, symbol);
  if (timeframe) {
    writeKey(TIMEFRAME_KEY, timeframe);
  }
}
