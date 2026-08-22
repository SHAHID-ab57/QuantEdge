import { describe, expect, it } from 'vitest';
import { deriveMarketStreamUrl } from './market-stream-url';

describe('deriveMarketStreamUrl', () => {
  it('converts http to ws and appends the gateway path', () => {
    expect(deriveMarketStreamUrl('http://localhost:8000')).toBe(
      'ws://localhost:8000/api/v1/ws/market',
    );
  });

  it('converts https to wss', () => {
    expect(deriveMarketStreamUrl('https://api.example.com')).toBe(
      'wss://api.example.com/api/v1/ws/market',
    );
  });

  it('replaces any existing path, query, and hash', () => {
    expect(deriveMarketStreamUrl('http://localhost:8000/foo?bar=1#baz')).toBe(
      'ws://localhost:8000/api/v1/ws/market',
    );
  });

  it('never derives a URL pointing at the exchange', () => {
    // Regression guard: NEXT_PUBLIC_WS_URL points at Delta's own public
    // socket, but this helper must only ever derive from the API URL.
    const result = deriveMarketStreamUrl('http://localhost:8000');
    expect(result).not.toContain('delta.exchange');
  });
});
