import { describe, expect, it } from 'vitest';
import {
  CandlePageSchema,
  CandleSchema,
  LatestCandleSchema,
  MarketListSchema,
  MarketResearchSchema,
  MarketSchema,
  TimeframesSchema,
} from './market';

const market = {
  id: '11111111-1111-4111-8111-111111111111',
  symbol: 'ETHUSD',
  exchange: 'Delta Exchange',
  exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
  base_asset: 'ETH',
  quote_asset: 'USD',
  market_type: 'perpetual',
  is_active: true,
  delta_product_id: 3136,
  delta_contract_type: 'perpetual_futures',
  tick_size: '0.05',
  funding_method: 'mark_price',
  funding_interval_seconds: 28800,
  listing_date: '2024-02-05T12:04:17Z',
};

const candle = {
  open_time: '2026-08-19T10:00:00Z',
  close_time: '2026-08-19T11:00:00Z',
  open: '3050.5',
  high: '3060',
  low: '3040',
  close: '3055.25',
  volume: '120.5',
  source: 'delta',
};

describe('MarketSchema', () => {
  it('accepts a valid market', () => {
    expect(MarketSchema.parse(market)).toEqual(market);
  });

  it('rejects an unknown market type', () => {
    expect(() => MarketSchema.parse({ ...market, market_type: 'futures' })).toThrow();
  });
});

describe('MarketListSchema', () => {
  it('accepts a market list', () => {
    const list = { markets: [market], total: 1 };
    expect(MarketListSchema.parse(list)).toEqual(list);
  });

  it('rejects a negative total', () => {
    expect(() => MarketListSchema.parse({ markets: [market], total: -1 })).toThrow();
  });
});

describe('TimeframesSchema', () => {
  it('accepts an empty timeframe list', () => {
    expect(TimeframesSchema.parse({ symbol: 'ETHUSD', timeframes: [] }).timeframes).toEqual([]);
  });
});

describe('MarketResearchSchema', () => {
  it('accepts research metrics with nullable timestamps', () => {
    const research = {
      symbol: 'ETHUSD',
      oldest_candle_at: '2026-08-13T00:00:00Z',
      newest_candle_at: '2026-08-20T17:00:00Z',
      coverage_days: 7.7,
      total_candles: 40000,
      timeframes: [
        {
          timeframe: '1h',
          stored_candles: 5000,
          oldest_at: '2026-08-13T00:00:00Z',
          newest_at: '2026-08-20T17:00:00Z',
          coverage_days: 7.0,
          expected_candles: 5000,
          missing_candles: 0,
          completeness: 100,
          average_daily_candles: 714.3,
        },
      ],
    };
    const parsed = MarketResearchSchema.parse(research);
    const first = parsed.timeframes[0];
    expect(first?.missing_candles).toBe(0);
    expect(parsed.coverage_days).toBe(7.7);
  });

  it('accepts an empty market with no timeframes', () => {
    const parsed = MarketResearchSchema.parse({
      symbol: 'ETHUSD',
      oldest_candle_at: null,
      newest_candle_at: null,
      coverage_days: null,
      total_candles: 0,
      timeframes: [],
    });
    expect(parsed.total_candles).toBe(0);
  });
});

describe('CandleSchema', () => {
  it('accepts a valid candle with optional fields absent', () => {
    expect(CandleSchema.parse(candle).close).toBe('3055.25');
  });
});

describe('CandlePageSchema', () => {
  it('parses pagination metadata', () => {
    const page = {
      symbol: 'ETHUSD',
      timeframe: '1h',
      items: [candle],
      pagination: { total: 42, returned: 1, has_more: true, limit: 1, offset: 0 },
    };
    expect(CandlePageSchema.parse(page).pagination.total).toBe(42);
  });
});

describe('LatestCandleSchema', () => {
  it('accepts a latest candle response', () => {
    const latest = { symbol: 'ETHUSD', timeframe: '1h', candle };
    expect(LatestCandleSchema.parse(latest).candle.close).toBe('3055.25');
  });
});
