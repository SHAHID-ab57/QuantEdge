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

export const MarketStreamSnapshotSchema = z.object({
  type: z.literal('snapshot'),
  symbol: z.string(),
  trade: LiveTradeDataSchema.nullable(),
  ticker: LiveTickerDataSchema.nullable(),
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
  MarketStreamPongSchema,
  MarketStreamErrorSchema,
]);

export type MarketStreamMessage = z.infer<typeof MarketStreamMessageSchema>;
