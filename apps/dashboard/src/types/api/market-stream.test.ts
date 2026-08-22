import { describe, expect, it } from 'vitest';
import {
  LiveTickerDataSchema,
  LiveTradeDataSchema,
  MarketStreamMessageSchema,
} from './market-stream';

const trade = {
  price: '2405.9',
  size: '100.0',
  side: 'buy',
  event_time: '2026-08-22T15:26:05.504024Z',
};

const ticker = {
  last_price: '2405.65',
  bid: '2405.6',
  ask: '2405.7',
  mark_price: '2405.59478316',
  price_change_24h: '0.2067',
  event_time: '2026-08-22T15:26:05.149014Z',
};

describe('LiveTradeDataSchema / LiveTickerDataSchema', () => {
  it('accepts a real gateway trade payload', () => {
    expect(LiveTradeDataSchema.safeParse(trade).success).toBe(true);
  });

  it('accepts a real gateway ticker payload', () => {
    expect(LiveTickerDataSchema.safeParse(ticker).success).toBe(true);
  });

  /**
   * Pins the exact contract behind a bug where every trade/ticker/snapshot
   * frame was silently dropped: the gateway used to emit `event_time` with a
   * `+00:00` offset (Python's plain `datetime.isoformat()`), and
   * `z.string().datetime()` accepts only a literal `Z` suffix by default —
   * so every single live frame failed validation while heartbeat pongs (no
   * timestamp) kept succeeding, making the connection look healthy with no
   * data ever arriving. Fixed at the source in
   * `services/api/app/marketdata/gateway.py`'s `_isoformat_utc`, which now
   * matches the REST layer's own `Z`-suffix convention
   * (`app/schemas/market_data.py`).
   *
   * This test intentionally keeps the schema strict rather than loosening it
   * to accept `+00:00` — a regression back to offset timestamps must fail
   * loudly here, not be silently tolerated by the frontend.
   */
  it('rejects the old +00:00-offset format that caused every live frame to be dropped', () => {
    const offsetTrade = { ...trade, event_time: '2026-08-22T15:26:05.504024+00:00' };
    expect(LiveTradeDataSchema.safeParse(offsetTrade).success).toBe(false);
  });
});

describe('MarketStreamMessageSchema', () => {
  it('accepts a real trade frame', () => {
    const result = MarketStreamMessageSchema.safeParse({
      type: 'trade',
      symbol: 'ETHUSD',
      data: trade,
    });
    expect(result.success).toBe(true);
  });

  it('accepts a real ticker frame', () => {
    const result = MarketStreamMessageSchema.safeParse({
      type: 'ticker',
      symbol: 'ETHUSD',
      data: ticker,
    });
    expect(result.success).toBe(true);
  });

  it('accepts a real snapshot frame with both trade and ticker', () => {
    const result = MarketStreamMessageSchema.safeParse({
      type: 'snapshot',
      symbol: 'ETHUSD',
      trade,
      ticker,
    });
    expect(result.success).toBe(true);
  });

  it('accepts a snapshot with null trade/ticker (fresh state)', () => {
    const result = MarketStreamMessageSchema.safeParse({
      type: 'snapshot',
      symbol: 'ETHUSD',
      trade: null,
      ticker: null,
    });
    expect(result.success).toBe(true);
  });

  it('accepts a pong frame', () => {
    expect(MarketStreamMessageSchema.safeParse({ type: 'pong' }).success).toBe(true);
  });
});
