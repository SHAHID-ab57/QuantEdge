import { describe, expect, it } from 'vitest';
import {
  CandlePageSchema,
  CandleSchema,
  LatestCandleSchema,
  MarketListSchema,
  MarketSchema,
  TimeframesSchema,
} from './market';

const market = {
  id: '11111111-1111-4111-8111-111111111111',
  symbol: 'ETHUSD',
  exchange: 'Delta Exchange',
  base_asset: 'ETH',
  quote_asset: 'USD',
  market_type: 'perpetual',
  is_active: true,
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
