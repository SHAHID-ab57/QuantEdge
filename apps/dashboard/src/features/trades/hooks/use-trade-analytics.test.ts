import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as useNowModule from '@/features/markets/hooks/use-now';
import { useTradeAnalytics } from './use-trade-analytics';

/**
 * Mocked so the "ages out on a wall-clock tick" test can force a
 * recompute without any new trade arriving, by changing the returned
 * value and re-rendering — deterministic, with no real waiting and no
 * fake-timer interaction at all. Every other test lets it track real
 * time via `mockImplementation(() => Date.now())` in `beforeEach`, since
 * they only care about `now` at the moment a trade-driven render happens.
 */
vi.mock('@/features/markets/hooks/use-now', () => ({
  useNow: vi.fn(),
}));

/**
 * Uses real timers + `waitFor`, not `vi.useFakeTimers()` — the same
 * pattern the page-level integration tests (`live-market-page.test.tsx`,
 * `order-book-page.test.tsx`) already rely on for streaming state.
 * `use-market-stream.test.ts` itself uses fake timers successfully, but
 * this hook additionally layers a real 1-second `useNow` tick on top of
 * the rAF-batched flush, and driving *two* independent timer mechanisms
 * through `vi.advanceTimersByTime` proved unreliable in practice — the
 * commit would intermittently not observably land before the next
 * assertion despite `act()` wrapping the advance. Real timers with
 * `waitFor` sidesteps that entirely: the calculations themselves (VWAP,
 * rolling windows, session accumulation) are exhaustively covered without
 * any timer involved at all in `lib/session-stats.test.ts` and
 * `lib/rolling-window.test.ts`; this file only has to prove the hook
 * *wires them up correctly* — every trade reaches the accumulator via
 * `onTrade`, a symbol change resets it, and the tape is capped
 * independently of analytics accuracy.
 */
class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  triggerOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  triggerMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

function latestSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) {
    throw new Error('no FakeWebSocket instance created yet');
  }
  return socket;
}

function tradeAt(price: string, size: string, isoTime: string, side = 'buy') {
  return {
    type: 'trade',
    symbol: 'ETHUSD',
    data: { price, size, side, event_time: isoTime },
  };
}

const mockedUseNow = vi.mocked(useNowModule.useNow);

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
  mockedUseNow.mockImplementation(() => Date.now());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useTradeAnalytics', () => {
  it('subscribes over the backend gateway, never the exchange directly', () => {
    renderHook(() => useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }));
    const socket = latestSocket();
    expect(socket.url).not.toContain('delta.exchange');
    expect(socket.url).toBe('ws://test/ws/market');
  });

  it('accumulates buy and sell volume across multiple trades', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    act(() => latestSocket().triggerMessage(tradeAt('100', '2', new Date().toISOString(), 'buy')));
    act(() => latestSocket().triggerMessage(tradeAt('100', '3', new Date().toISOString(), 'sell')));

    await waitFor(() => expect(result.current.sessionStats.tradeCount).toBe(2));
    expect(result.current.sessionStats.buyVolume).toBe(2);
    expect(result.current.sessionStats.sellVolume).toBe(3);
  });

  it('never loses a trade to a burst delivered within one tick', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    act(() => {
      for (let i = 0; i < 10; i += 1) {
        latestSocket().triggerMessage(tradeAt('100', '1', new Date().toISOString(), 'buy'));
      }
    });

    await waitFor(() => expect(result.current.sessionStats.tradeCount).toBe(10));
    expect(result.current.sessionStats.buyVolume).toBe(10);
  });

  it('computes session VWAP as cumulative notional over cumulative volume', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    act(() => latestSocket().triggerMessage(tradeAt('100', '2', new Date().toISOString())));
    act(() => latestSocket().triggerMessage(tradeAt('200', '1', new Date().toISOString())));

    await waitFor(() => expect(result.current.vwap.session).toBeCloseTo(133.333, 2));
  });

  it('tracks the largest trade by notional value', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    act(() => latestSocket().triggerMessage(tradeAt('1000', '1', new Date().toISOString()))); // value 1000
    act(() => latestSocket().triggerMessage(tradeAt('1', '5', new Date().toISOString()))); // value 5

    await waitFor(() => expect(result.current.sessionStats.largestTrade?.value).toBe(1000));
  });

  it('excludes a trade older than 1 minute from the rolling VWAP/analytics', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    const twoMinutesAgo = new Date(Date.now() - 2 * 60_000).toISOString();
    act(() => latestSocket().triggerMessage(tradeAt('999', '50', twoMinutesAgo)));
    act(() => latestSocket().triggerMessage(tradeAt('100', '1', new Date().toISOString())));

    await waitFor(() => expect(result.current.rolling.tradesPerMinute).toBe(1));
    expect(result.current.vwap.oneMinute).toBeCloseTo(100);
  });

  it('still includes an out-of-1-minute-window trade in the 15-minute VWAP', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    const twoMinutesAgo = new Date(Date.now() - 2 * 60_000).toISOString();
    act(() => latestSocket().triggerMessage(tradeAt('999', '50', twoMinutesAgo)));
    act(() => latestSocket().triggerMessage(tradeAt('100', '1', new Date().toISOString())));

    await waitFor(() => expect(result.current.vwap.fifteenMinute).not.toBeNull());
    expect(result.current.vwap.fifteenMinute).not.toBeCloseTo(100); // the old 999 trade still weighs in
  });

  it('ages the rolling window out on a wall-clock tick even with no new trade', async () => {
    const { result, rerender } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeAt('100', '1', new Date().toISOString())));
    await waitFor(() => expect(result.current.rolling.tradesPerMinute).toBe(1));

    // No new trade arrives; the wall clock alone advances past the window.
    mockedUseNow.mockImplementation(() => Date.now() + 2 * 60_000);
    rerender();

    expect(result.current.rolling.tradesPerMinute).toBe(0);
    expect(result.current.vwap.oneMinute).toBeNull();
  });

  it('resets every accumulator when the symbol changes', async () => {
    const { result, rerender } = renderHook(
      ({ symbol }) => useTradeAnalytics(symbol, { streamUrl: 'ws://test/ws/market' }),
      { initialProps: { symbol: 'ETHUSD' } },
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeAt('100', '5', new Date().toISOString())));
    await waitFor(() => expect(result.current.sessionStats.tradeCount).toBe(1));

    rerender({ symbol: 'BTCUSD' });

    expect(result.current.sessionStats.tradeCount).toBe(0);
    expect(result.current.vwap.session).toBeNull();
    expect(result.current.rolling.tradesPerMinute).toBe(0);
  });

  it('derives market sentiment from the rolling imbalance', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeAt('100', '10', new Date().toISOString(), 'buy')));

    await waitFor(() => expect(result.current.sentiment.label).toBe('strongly-bullish'));
  });

  it('accumulates sparkline history samples as trades arrive', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeAt('100', '1', new Date().toISOString())));

    await waitFor(() => expect(result.current.history.timestamps.length).toBeGreaterThan(0));
  });

  it('closes its socket and stops reconnecting on unmount, leaving nothing running', async () => {
    const { result, unmount } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerMessage(tradeAt('100', '1', new Date().toISOString())));
    await waitFor(() => expect(result.current.sessionStats.tradeCount).toBe(1));

    const socketsBefore = FakeWebSocket.instances.length;
    unmount();

    expect(latestSocket().readyState).toBe(FakeWebSocket.CLOSED);
    // The close handler must not schedule a reconnect for an unmounted hook.
    expect(FakeWebSocket.instances).toHaveLength(socketsBefore);
  });

  it('caps the displayed tape at maxTapeRows independent of analytics accuracy', async () => {
    const { result } = renderHook(() =>
      useTradeAnalytics('ETHUSD', { streamUrl: 'ws://test/ws/market', maxTapeRows: 2 }),
    );
    act(() => latestSocket().triggerOpen());

    act(() => latestSocket().triggerMessage(tradeAt('100', '1', new Date().toISOString())));
    act(() => latestSocket().triggerMessage(tradeAt('101', '1', new Date().toISOString())));
    act(() => latestSocket().triggerMessage(tradeAt('102', '1', new Date().toISOString())));

    await waitFor(() => expect(result.current.sessionStats.tradeCount).toBe(3));
    // The tape is capped...
    expect(result.current.trades).toHaveLength(2);
    // ...but every trade still contributed to the session accumulator.
  });
});
