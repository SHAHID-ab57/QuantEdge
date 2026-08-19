import { z } from 'zod';

export const MarketSchema = z.object({
  id: z.string().uuid(),
  symbol: z.string(),
  exchange: z.string(),
  base_asset: z.string(),
  quote_asset: z.string(),
  market_type: z.enum(['spot', 'perpetual', 'expiry']),
  is_active: z.boolean(),
});

export type Market = z.infer<typeof MarketSchema>;

export const MarketListSchema = z.object({
  markets: z.array(MarketSchema),
  total: z.number().int().nonnegative(),
});

export type MarketList = z.infer<typeof MarketListSchema>;

export const TimeframesSchema = z.object({
  symbol: z.string(),
  timeframes: z.array(z.string()),
});

export type Timeframes = z.infer<typeof TimeframesSchema>;

export const CandleSchema = z.object({
  open_time: z.string().datetime(),
  close_time: z.string().datetime(),
  open: z.string(),
  high: z.string(),
  low: z.string(),
  close: z.string(),
  volume: z.string(),
  quote_volume: z.string().nullable().optional(),
  trade_count: z.number().int().nullable().optional(),
  source: z.string(),
});

export type Candle = z.infer<typeof CandleSchema>;

export const PaginationSchema = z.object({
  total: z.number().int().nonnegative(),
  returned: z.number().int().nonnegative(),
  has_more: z.boolean(),
  limit: z.number().int().nonnegative(),
  offset: z.number().int().nonnegative(),
});

export type Pagination = z.infer<typeof PaginationSchema>;

export const CandlePageSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  items: z.array(CandleSchema),
  pagination: PaginationSchema,
});

export type CandlePage = z.infer<typeof CandlePageSchema>;

export const LatestCandleSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  candle: CandleSchema,
});

export type LatestCandle = z.infer<typeof LatestCandleSchema>;
