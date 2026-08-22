import { afterEach, describe, expect, it, vi } from 'vitest';
import { readRememberedMarket, rememberMarket } from './remembered-market';

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe('remembered market', () => {
  it('round-trips a symbol and timeframe', () => {
    rememberMarket('ETHUSD', '1m');
    expect(readRememberedMarket()).toEqual({ symbol: 'ETHUSD', timeframe: '1m' });
  });

  it('reports nulls when nothing has been stored', () => {
    expect(readRememberedMarket()).toEqual({ symbol: null, timeframe: null });
  });

  it('keeps the previous timeframe when none is supplied', () => {
    rememberMarket('ETHUSD', '1h');
    rememberMarket('BTCUSD', null);
    expect(readRememberedMarket()).toEqual({ symbol: 'BTCUSD', timeframe: '1h' });
  });

  it('degrades to nulls when storage reads throw (private browsing)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    expect(readRememberedMarket()).toEqual({ symbol: null, timeframe: null });
  });

  it('does not throw when storage writes are blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    expect(() => rememberMarket('ETHUSD', '1m')).not.toThrow();
  });
});
