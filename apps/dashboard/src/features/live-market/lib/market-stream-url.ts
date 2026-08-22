const MARKET_STREAM_PATH = '/api/v1/ws/market';

/**
 * Derives the backend's live market-stream WebSocket URL from the same
 * `NEXT_PUBLIC_API_URL` the REST client already uses — never from
 * `NEXT_PUBLIC_WS_URL` (that variable points at Delta Exchange's own
 * public socket and is intentionally unused; the frontend must never talk
 * to the exchange directly). Deriving from the API URL means there is no
 * separate config value a misconfiguration could point at the exchange.
 */
export function deriveMarketStreamUrl(apiUrl: string): string {
  const url = new URL(apiUrl);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = MARKET_STREAM_PATH;
  url.search = '';
  url.hash = '';
  return url.toString();
}
