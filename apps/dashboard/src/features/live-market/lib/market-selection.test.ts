import { describe, expect, it } from 'vitest';
import type { Market } from '@/types/api/market';
import {
  MAX_CANDIDATES,
  PRIMARY_RESEARCH_SYMBOL,
  assessMarket,
  buildCandidateSymbols,
  selectResearchMarket,
  type MarketReadiness,
} from './market-selection';

function market(symbol: string, isActive = true): Market {
  return {
    id: `00000000-0000-4000-8000-${symbol.padEnd(12, '0').slice(0, 12)}`,
    symbol,
    exchange: 'Delta Exchange',
    exchange_id: '6b698660-361c-4e09-80cb-79005d4c0a65',
    base_asset: symbol.replace('USD', ''),
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: isActive,
    delta_product_id: 1,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.05',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: null,
  };
}

const LIVE = { ETHUSD: '1900', BTCUSD: '77000' };

function readiness(overrides: Partial<MarketReadiness> = {}): MarketReadiness {
  return {
    symbol: 'ETHUSD',
    hasHistoricalCandles: true,
    hasLiveSupport: true,
    hasLatestPrice: true,
    isPending: false,
    isReady: true,
    blockers: [],
    ...overrides,
  };
}

describe('assessMarket', () => {
  it('marks a market with candles and a live feed as ready', () => {
    const result = assessMarket({
      symbol: 'ETHUSD',
      timeframes: ['1m', '1h'],
      livePrices: LIVE,
    });
    expect(result.isReady).toBe(true);
    expect(result.blockers).toEqual([]);
  });

  it('reports missing candles as a blocker', () => {
    const result = assessMarket({ symbol: 'ETHUSD', timeframes: [], livePrices: LIVE });
    expect(result.isReady).toBe(false);
    expect(result.hasHistoricalCandles).toBe(false);
    expect(result.blockers.join(' ')).toMatch(/No historical candles/);
  });

  it('reports an untracked symbol as having no live feed', () => {
    const result = assessMarket({
      symbol: '1000BONKUSD',
      timeframes: ['1m'],
      livePrices: LIVE,
    });
    expect(result.hasLiveSupport).toBe(false);
    expect(result.blockers.join(' ')).toMatch(/not on the backend live feed/);
  });

  it('distinguishes a tracked symbol with no price yet from an untracked one', () => {
    const result = assessMarket({
      symbol: 'SOLUSD',
      timeframes: ['1m'],
      livePrices: { ...LIVE, SOLUSD: '' },
    });
    expect(result.hasLiveSupport).toBe(true);
    expect(result.hasLatestPrice).toBe(false);
    expect(result.blockers.join(' ')).toMatch(/has not received a price yet/);
  });

  it('stays pending, without blockers, while the probe is in flight', () => {
    const result = assessMarket({ symbol: 'ETHUSD', timeframes: undefined, livePrices: LIVE });
    expect(result.isPending).toBe(true);
    expect(result.isReady).toBe(false);
    expect(result.blockers).toEqual([]);
  });
});

describe('buildCandidateSymbols', () => {
  const markets = [market('1000BONKUSD'), market('ETHUSD'), market('BTCUSD'), market('ZZZUSD')];

  it('puts the requested symbol first', () => {
    const order = buildCandidateSymbols({
      requested: 'BTCUSD',
      remembered: null,
      markets,
      livePrices: LIVE,
    });
    expect(order[0]).toBe('BTCUSD');
  });

  it('falls back to the remembered symbol, then the primary research market', () => {
    const order = buildCandidateSymbols({
      requested: null,
      remembered: 'BTCUSD',
      markets,
      livePrices: LIVE,
    });
    expect(order[0]).toBe('BTCUSD');
    expect(order[1]).toBe(PRIMARY_RESEARCH_SYMBOL);
  });

  it('prefers ETHUSD over the alphabetically-first market when nothing is requested', () => {
    const order = buildCandidateSymbols({
      requested: null,
      remembered: null,
      markets,
      livePrices: LIVE,
    });
    expect(order[0]).toBe('ETHUSD');
    expect(order.indexOf('1000BONKUSD')).toBeGreaterThan(order.indexOf('ETHUSD'));
  });

  it('ranks live-tracked symbols ahead of untracked ones', () => {
    const order = buildCandidateSymbols({
      requested: null,
      remembered: null,
      markets,
      livePrices: LIVE,
    });
    expect(order.indexOf('BTCUSD')).toBeLessThan(order.indexOf('ZZZUSD'));
  });

  it('drops unknown and inactive symbols', () => {
    const order = buildCandidateSymbols({
      requested: 'NOTAMARKET',
      remembered: null,
      markets: [...markets, market('DEADUSD', false)],
      livePrices: LIVE,
    });
    expect(order).not.toContain('NOTAMARKET');
    expect(order).not.toContain('DEADUSD');
  });

  it('never repeats a symbol and caps the list', () => {
    const many = Array.from({ length: 30 }, (_, index) => market(`SYM${index}USD`));
    const order = buildCandidateSymbols({
      requested: 'SYM1USD',
      remembered: 'SYM1USD',
      markets: many,
      livePrices: {},
    });
    expect(order).toHaveLength(MAX_CANDIDATES);
    expect(new Set(order).size).toBe(order.length);
  });

  it('returns nothing when the market list has not loaded', () => {
    expect(
      buildCandidateSymbols({
        requested: 'ETHUSD',
        remembered: null,
        markets: undefined,
        livePrices: LIVE,
      }),
    ).toEqual([]);
  });
});

describe('selectResearchMarket', () => {
  it('picks the first fully ready candidate', () => {
    const selection = selectResearchMarket([
      readiness({ symbol: '1000BONKUSD', hasHistoricalCandles: false, isReady: false }),
      readiness({ symbol: 'ETHUSD' }),
    ]);
    expect(selection.symbol).toBe('ETHUSD');
  });

  it('waits rather than settling on a degraded market while a probe is pending', () => {
    const selection = selectResearchMarket([
      readiness({ symbol: '1000BONKUSD', hasHistoricalCandles: false, isReady: false }),
      readiness({ symbol: 'ETHUSD', isPending: true, isReady: false }),
    ]);
    expect(selection.symbol).toBeNull();
    expect(selection.isResolving).toBe(true);
  });

  it('falls back to a market with candles when none has a live feed', () => {
    const selection = selectResearchMarket([
      readiness({ symbol: 'AAAUSD', hasHistoricalCandles: false, isReady: false }),
      readiness({ symbol: 'ETHUSD', hasLiveSupport: false, isReady: false }),
    ]);
    expect(selection.symbol).toBe('ETHUSD');
  });

  it('never leaves the dashboard empty when candidates exist', () => {
    const selection = selectResearchMarket([
      readiness({
        symbol: 'AAAUSD',
        hasHistoricalCandles: false,
        hasLiveSupport: false,
        isReady: false,
      }),
    ]);
    expect(selection.symbol).toBe('AAAUSD');
    expect(selection.isResolving).toBe(false);
  });

  it('reports nothing when there are no candidates at all', () => {
    expect(selectResearchMarket([])).toEqual({
      symbol: null,
      readiness: null,
      isResolving: false,
    });
  });
});
