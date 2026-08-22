import { z } from 'zod';

/**
 * Wire schemas for `/api/v1/ws/market` (see `services/api/app/api/v1/endpoints/market_stream.py`
 * for the authoritative protocol description). Every inbound frame is
 * validated against these before the app trusts it, matching the same
 * convention as the REST client in `src/lib/api/market.ts`.
 */

export const LiveTradeDataSchema = z.object({
  price: z.string(),
  size: z.string(),
  side: z.string(),
  event_time: z.string().datetime(),
});

export type LiveTradeData = z.infer<typeof LiveTradeDataSchema>;

export const LiveTickerDataSchema = z.object({
  last_price: z.string().nullable(),
  bid: z.string().nullable(),
  ask: z.string().nullable(),
  mark_price: z.string().nullable(),
  price_change_24h: z.string().nullable(),
  event_time: z.string().datetime(),
});

export type LiveTickerData = z.infer<typeof LiveTickerDataSchema>;

export const OrderBookLevelSchema = z.object({
  price: z.string(),
  size: z.string(),
});

export type OrderBookLevelData = z.infer<typeof OrderBookLevelSchema>;

/**
 * Already sorted (bids descending, asks ascending) and depth-limited by the
 * gateway — see `services/api/app/marketdata/gateway.py`'s
 * `_ORDERBOOK_DEPTH` — and reconstructed from a snapshot + merged
 * incremental diffs (`app/marketdata/orderbook.py`'s `OrderBookAggregator`),
 * never a single raw exchange message.
 */
export const LiveOrderBookDataSchema = z.object({
  bids: z.array(OrderBookLevelSchema),
  asks: z.array(OrderBookLevelSchema),
  event_time: z.string().datetime().nullable(),
  sequence: z.number().int().nullable(),
});

export type LiveOrderBookData = z.infer<typeof LiveOrderBookDataSchema>;

export const MarketStreamSnapshotSchema = z.object({
  type: z.literal('snapshot'),
  symbol: z.string(),
  trade: LiveTradeDataSchema.nullable(),
  ticker: LiveTickerDataSchema.nullable(),
  orderbook: LiveOrderBookDataSchema.nullable(),
});

export const MarketStreamTradeSchema = z.object({
  type: z.literal('trade'),
  symbol: z.string(),
  data: LiveTradeDataSchema,
});

export const MarketStreamTickerSchema = z.object({
  type: z.literal('ticker'),
  symbol: z.string(),
  data: LiveTickerDataSchema,
});

export const MarketStreamOrderBookSchema = z.object({
  type: z.literal('orderbook'),
  symbol: z.string(),
  data: LiveOrderBookDataSchema,
});

export const MarketStreamPongSchema = z.object({
  type: z.literal('pong'),
});

export const MarketStreamErrorSchema = z.object({
  type: z.literal('error'),
  detail: z.string(),
});

export const MarketStreamMessageSchema = z.discriminatedUnion('type', [
  MarketStreamSnapshotSchema,
  MarketStreamTradeSchema,
  MarketStreamTickerSchema,
  MarketStreamOrderBookSchema,
  MarketStreamPongSchema,
  MarketStreamErrorSchema,
]);

export type MarketStreamMessage = z.infer<typeof MarketStreamMessageSchema>;
