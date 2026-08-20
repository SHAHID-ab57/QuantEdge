import { z } from 'zod';

export const MarketSchema = z.object({
  id: z.string().uuid(),
  symbol: z.string(),
  exchange: z.string(),
  exchange_id: z.string().uuid(),
  base_asset: z.string(),
  quote_asset: z.string(),
  market_type: z.enum(['spot', 'perpetual', 'expiry']),
  is_active: z.boolean(),
  delta_product_id: z.number().int().nullable(),
  delta_contract_type: z.string().nullable(),
  tick_size: z.string().nullable(),
  funding_method: z.string().nullable(),
  funding_interval_seconds: z.number().int().nullable(),
  listing_date: z.string().datetime().nullable(),
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

export const CandleStatisticsSchema = z.object({
  highest_price: z.string().nullable(),
  lowest_price: z.string().nullable(),
  highest_volume: z.string().nullable(),
  lowest_volume: z.string().nullable(),
  average_open: z.string().nullable(),
  average_close: z.string().nullable(),
  average_high: z.string().nullable(),
  average_low: z.string().nullable(),
  average_volume: z.string().nullable(),
  total_candles: z.number().int().nonnegative(),
  first_candle_at: z.string().datetime().nullable(),
  last_candle_at: z.string().datetime().nullable(),
  expected_candles: z.number().int().nonnegative(),
  missing_candles: z.number().int().nonnegative(),
  completeness: z.number().nullable(),
});

export type CandleStatistics = z.infer<typeof CandleStatisticsSchema>;

export const CandleQualitySchema = z.object({
  completeness_score: z.number(),
  freshness_score: z.number(),
  missing_interval_count: z.number().int().nonnegative(),
  missing_intervals: z.array(z.string().datetime()),
  duplicate_candles: z.number().int().nonnegative(),
  out_of_order_candles: z.number().int().nonnegative(),
  invalid_ohlc_candles: z.number().int().nonnegative(),
  gaps_detected: z.boolean(),
  overall_quality_score: z.number(),
});

export type CandleQuality = z.infer<typeof CandleQualitySchema>;

export const QueryMetadataSchema = z.object({
  execution_time_ms: z.number(),
  database_time_ms: z.number(),
  rows_scanned: z.number().int().nonnegative(),
  rows_returned: z.number().int().nonnegative(),
  cache_status: z.string(),
  generated_at: z.string().datetime(),
});

export type QueryMetadata = z.infer<typeof QueryMetadataSchema>;

export const CandlePageSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  items: z.array(CandleSchema),
  pagination: PaginationSchema,
  statistics: CandleStatisticsSchema,
  quality: CandleQualitySchema,
  meta: QueryMetadataSchema,
});

export type CandlePage = z.infer<typeof CandlePageSchema>;

export const LatestCandleSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  candle: CandleSchema,
});

export type LatestCandle = z.infer<typeof LatestCandleSchema>;

export const CandleStatsSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  start: z.string().datetime().nullable(),
  end: z.string().datetime().nullable(),
  total_candles: z.number().int().nonnegative(),
  highest_price: z.string().nullable(),
  lowest_price: z.string().nullable(),
  average_volume: z.string().nullable(),
  first_candle: CandleSchema.nullable(),
  last_candle: CandleSchema.nullable(),
});

export type CandleStats = z.infer<typeof CandleStatsSchema>;

export const ResearchTimeframeMetricsSchema = z.object({
  timeframe: z.string(),
  stored_candles: z.number().int().nonnegative(),
  oldest_at: z.string().datetime().nullable(),
  newest_at: z.string().datetime().nullable(),
  coverage_days: z.number().nullable(),
  expected_candles: z.number().int().nonnegative(),
  missing_candles: z.number().int().nonnegative(),
  completeness: z.number().nullable(),
  average_daily_candles: z.number().nullable(),
});

export type ResearchTimeframeMetrics = z.infer<typeof ResearchTimeframeMetricsSchema>;

export const MarketResearchSchema = z.object({
  symbol: z.string(),
  oldest_candle_at: z.string().datetime().nullable(),
  newest_candle_at: z.string().datetime().nullable(),
  coverage_days: z.number().nullable(),
  total_candles: z.number().int().nonnegative(),
  timeframes: z.array(ResearchTimeframeMetricsSchema),
});

export type MarketResearch = z.infer<typeof MarketResearchSchema>;
