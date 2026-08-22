import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useMarketStream } from './use-market-stream';

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

  triggerServerClose() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}

function latestSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) {
    throw new Error('no FakeWebSocket instance created yet');
  }
  return socket;
}

/**
 * The hook batches via `requestAnimationFrame`, not a fixed timer — Vitest's
 * fake timers fake `requestAnimationFrame` too, so advancing by one frame's
 * worth of time is enough to flush a pending commit deterministically,
 * without any real waiting.
 */
const ONE_FRAME_MS = 20;

/**
 * Delivers a frame and drains the hook's update buffer. Stream updates are
 * batched rather than committed per message (see the hook's own docstring),
 * so a test that asserts immediately after `triggerMessage` would be
 * racing the flush rather than testing anything.
 */
function deliver(payload: unknown) {
  act(() => {
    latestSocket().triggerMessage(payload);
    vi.advanceTimersByTime(ONE_FRAME_MS);
  });
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('useMarketStream', () => {
  it('connects and subscribes to the symbol once the socket opens', () => {
    renderHook(() => useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }));
    const socket = latestSocket();
    expect(socket.url).toBe('ws://test/ws/market');

    act(() => socket.triggerOpen());

    expect(socket.sent).toHaveLength(1);
    expect(JSON.parse(socket.sent[0]!)).toEqual({ action: 'subscribe', symbols: ['ETHUSD'] });
  });

  it('reports connectionState transitions: connecting -> open', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    expect(result.current.connectionState).toBe('connecting');

    act(() => latestSocket().triggerOpen());
    expect(result.current.connectionState).toBe('open');
  });

  it('updates latestTrade and prepends to the capped trade tape', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market', maxTrades: 2 }),
    );
    act(() => latestSocket().triggerOpen());

    deliver({
      type: 'trade',
      symbol: 'ETHUSD',
      data: { price: '100', size: '1', side: 'unknown', event_time: '2026-01-01T00:00:00Z' },
    });
    expect(result.current.latestTrade?.price).toBe('100');
    expect(result.current.trades).toHaveLength(1);

    deliver({
      type: 'trade',
      symbol: 'ETHUSD',
      data: { price: '101', size: '1', side: 'unknown', event_time: '2026-01-01T00:00:01Z' },
    });
    deliver({
      type: 'trade',
      symbol: 'ETHUSD',
      data: { price: '102', size: '1', side: 'unknown', event_time: '2026-01-01T00:00:02Z' },
    });

    // Capped at maxTrades=2, newest first.
    expect(result.current.trades).toHaveLength(2);
    expect(result.current.trades[0]?.price).toBe('102');
    expect(result.current.trades[1]?.price).toBe('101');
  });

  it('updates latestTicker from a ticker message', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    deliver({
      type: 'ticker',
      symbol: 'ETHUSD',
      data: {
        last_price: '1900',
        bid: '1899',
        ask: '1901',
        mark_price: '1900.5',
        price_change_24h: '3.2',
        event_time: '2026-01-01T00:00:00Z',
      },
    });

    expect(result.current.latestTicker?.last_price).toBe('1900');
  });

  it('applies a snapshot without adding a trade-tape row', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    deliver({
      type: 'snapshot',
      symbol: 'ETHUSD',
      trade: { price: '100', size: '1', side: 'unknown', event_time: '2026-01-01T00:00:00Z' },
      ticker: null,
      orderbook: null,
    });

    expect(result.current.latestTrade?.price).toBe('100');
    expect(result.current.trades).toHaveLength(0);
  });

  it('ignores a message that fails schema validation', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    deliver({ type: 'trade', symbol: 'ETHUSD', data: {} });

    expect(result.current.latestTrade).toBeNull();
  });

  it('ignores a frame that is not valid JSON', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().onmessage?.({ data: 'not json' }));

    expect(result.current.latestTrade).toBeNull();
  });

  it('reconnects with backoff after the socket closes', () => {
    renderHook(() => useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }));
    const first = latestSocket();
    act(() => first.triggerOpen());

    act(() => first.triggerServerClose());
    expect(FakeWebSocket.instances).toHaveLength(1); // no reconnect yet

    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeWebSocket.instances).toHaveLength(2); // first backoff: 1s
  });

  it('reports connectionState as reconnecting with an incrementing attempt count', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerServerClose());

    expect(result.current.connectionState).toBe('reconnecting');
    expect(result.current.reconnectAttempt).toBe(1);
  });

  it('resets reconnectAttempt to 0 after a successful reconnection', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => latestSocket().triggerServerClose());
    act(() => vi.advanceTimersByTime(1_000));
    act(() => latestSocket().triggerOpen());

    expect(result.current.connectionState).toBe('open');
    expect(result.current.reconnectAttempt).toBe(0);
  });

  it('sends a ping on the heartbeat interval while open', () => {
    renderHook(() => useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }));
    const socket = latestSocket();
    act(() => socket.triggerOpen());
    socket.sent = []; // clear the subscribe message

    act(() => vi.advanceTimersByTime(15_000));

    expect(socket.sent).toHaveLength(1);
    expect(JSON.parse(socket.sent[0]!)).toEqual({ action: 'ping' });
  });

  it('resets trade/ticker state and reconnects when the symbol changes', () => {
    const { result, rerender } = renderHook(
      ({ symbol }) =>
        useMarketStream(symbol, {
          streamUrl: 'ws://test/ws/market',
        }),
      { initialProps: { symbol: 'ETHUSD' } },
    );

    act(() => latestSocket().triggerOpen());
    deliver({
      type: 'trade',
      symbol: 'ETHUSD',
      data: { price: '100', size: '1', side: 'unknown', event_time: '2026-01-01T00:00:00Z' },
    });
    expect(result.current.latestTrade).not.toBeNull();

    rerender({ symbol: 'BTCUSD' });

    expect(result.current.latestTrade).toBeNull();
    expect(result.current.trades).toEqual([]);
    const newSocket = latestSocket();
    act(() => newSocket.triggerOpen());
    expect(JSON.parse(newSocket.sent[0]!)).toEqual({ action: 'subscribe', symbols: ['BTCUSD'] });
  });

  it('ignores frames for a different symbol than the one subscribed', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    deliver({
      type: 'trade',
      symbol: 'BTCUSD',
      data: { price: '77000', size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
    });

    // A BTC print must never be attributed to the ETH view.
    expect(result.current.latestTrade).toBeNull();
    expect(result.current.trades).toEqual([]);
  });

  it('coalesces a burst of trades into a single state commit', () => {
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' });
    });
    act(() => latestSocket().triggerOpen());
    const before = renders;

    act(() => {
      for (let i = 0; i < 20; i += 1) {
        latestSocket().triggerMessage({
          type: 'trade',
          symbol: 'ETHUSD',
          data: {
            price: String(100 + i),
            size: '1',
            side: 'buy',
            event_time: `2026-01-01T00:00:${String(i).padStart(2, '0')}Z`,
          },
        });
      }
      vi.advanceTimersByTime(ONE_FRAME_MS);
    });

    // All 20 prints land, but as one commit rather than twenty.
    expect(result.current.trades).toHaveLength(20);
    expect(renders - before).toBeLessThanOrEqual(2);
  });

  it('keeps buffered trades newest-first across a batch', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    act(() => {
      for (const price of ['100', '101', '102']) {
        latestSocket().triggerMessage({
          type: 'trade',
          symbol: 'ETHUSD',
          data: { price, size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
        });
      }
      vi.advanceTimersByTime(ONE_FRAME_MS);
    });

    expect(result.current.trades.map((trade) => trade.price)).toEqual(['102', '101', '100']);
    expect(result.current.latestTrade?.price).toBe('102');
  });

  it('measures heartbeat round-trip latency from ping to pong', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    expect(result.current.latencyMs).toBeNull();

    act(() => vi.advanceTimersByTime(15_000)); // fires the ping
    act(() => {
      vi.advanceTimersByTime(40); // server think time
      latestSocket().triggerMessage({ type: 'pong' });
      vi.advanceTimersByTime(ONE_FRAME_MS);
    });

    expect(result.current.latencyMs).toBe(40);
  });

  it('records the time of the last trade separately from the last message', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    deliver({ type: 'pong' });

    expect(result.current.lastMessageAt).not.toBeNull();
    expect(result.current.lastTradeAt).toBeNull();

    deliver({
      type: 'trade',
      symbol: 'ETHUSD',
      data: { price: '100', size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
    });
    expect(result.current.lastTradeAt).not.toBeNull();
  });

  it('does not connect at all when symbol is null', () => {
    renderHook(() => useMarketStream(null, { streamUrl: 'ws://test/ws/market' }));
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('closes the socket and stops reconnecting on unmount', () => {
    const { unmount } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    const socket = latestSocket();
    act(() => socket.triggerOpen());

    unmount();
    expect(socket.readyState).toBe(FakeWebSocket.CLOSED);

    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeWebSocket.instances).toHaveLength(1); // no reconnect after unmount
  });

  it('caps the reconnect delay at MAX_RECONNECT_DELAY_MS', async () => {
    renderHook(() => useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }));

    // Force several consecutive failures to blow past the cap.
    for (let i = 0; i < 6; i += 1) {
      const socket = latestSocket();
      act(() => socket.triggerServerClose());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
    }

    // Every attempt should have produced exactly one new socket per 30s tick
    // once the delay is capped — i.e. no runaway/instant reconnect storm.
    expect(FakeWebSocket.instances.length).toBeLessThanOrEqual(7);
  });

  it('exposes the latest order book from an orderbook message', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    deliver({
      type: 'orderbook',
      symbol: 'ETHUSD',
      data: {
        bids: [{ price: '100', size: '1' }],
        asks: [{ price: '101', size: '2' }],
        event_time: '2026-01-01T00:00:00Z',
        sequence: 42,
      },
    });

    expect(result.current.latestOrderBook?.bids).toEqual([{ price: '100', size: '1' }]);
    expect(result.current.latestOrderBook?.sequence).toBe(42);
  });

  it('takes the order book from a snapshot when no update has streamed yet', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());

    deliver({
      type: 'snapshot',
      symbol: 'ETHUSD',
      trade: null,
      ticker: null,
      orderbook: {
        bids: [{ price: '100', size: '1' }],
        asks: [],
        event_time: '2026-01-01T00:00:00Z',
        sequence: 1,
      },
    });

    expect(result.current.latestOrderBook?.bids).toEqual([{ price: '100', size: '1' }]);
  });

  it('resets the order book to null when the symbol changes', () => {
    const { result, rerender } = renderHook(
      ({ symbol }) => useMarketStream(symbol, { streamUrl: 'ws://test/ws/market' }),
      { initialProps: { symbol: 'ETHUSD' } },
    );
    act(() => latestSocket().triggerOpen());
    deliver({
      type: 'orderbook',
      symbol: 'ETHUSD',
      data: { bids: [{ price: '100', size: '1' }], asks: [], event_time: null, sequence: null },
    });
    expect(result.current.latestOrderBook).not.toBeNull();

    rerender({ symbol: 'BTCUSD' });
    expect(result.current.latestOrderBook).toBeNull();
  });
});

describe('useMarketStream batching (requestAnimationFrame)', () => {
  it('schedules the commit via requestAnimationFrame, not a fixed timer', () => {
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame');
    renderHook(() => useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }));
    act(() => latestSocket().triggerOpen());
    rafSpy.mockClear();

    act(() => {
      latestSocket().triggerMessage({
        type: 'trade',
        symbol: 'ETHUSD',
        data: { price: '100', size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
      });
    });

    expect(rafSpy).toHaveBeenCalledTimes(1);
    rafSpy.mockRestore();
  });

  it('coalesces a burst within one frame into a single requestAnimationFrame call', () => {
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame');
    renderHook(() => useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }));
    act(() => latestSocket().triggerOpen());
    rafSpy.mockClear();

    act(() => {
      for (let i = 0; i < 10; i += 1) {
        latestSocket().triggerMessage({
          type: 'trade',
          symbol: 'ETHUSD',
          data: {
            price: String(100 + i),
            size: '1',
            side: 'buy',
            event_time: '2026-01-01T00:00:00Z',
          },
        });
      }
    });

    // Ten messages before the frame fires still schedule only one commit.
    expect(rafSpy).toHaveBeenCalledTimes(1);
    rafSpy.mockRestore();
  });

  it('cancels a pending frame on unmount rather than leaking it', () => {
    const cancelSpy = vi.spyOn(globalThis, 'cancelAnimationFrame');
    const { unmount } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => {
      latestSocket().triggerMessage({
        type: 'trade',
        symbol: 'ETHUSD',
        data: { price: '100', size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
      });
    });

    unmount();

    expect(cancelSpy).toHaveBeenCalled();
    cancelSpy.mockRestore();
  });
});

describe('useMarketStream channels option', () => {
  it('defaults to tracking every channel', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', { streamUrl: 'ws://test/ws/market' }),
    );
    act(() => latestSocket().triggerOpen());
    deliver({
      type: 'trade',
      symbol: 'ETHUSD',
      data: { price: '100', size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
    });
    expect(result.current.latestTrade?.price).toBe('100');
  });

  it('drops a trade message entirely when the trades channel is disabled', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', {
        streamUrl: 'ws://test/ws/market',
        channels: { trades: false, ticker: false, orderBook: true },
      }),
    );
    act(() => latestSocket().triggerOpen());
    deliver({
      type: 'trade',
      symbol: 'ETHUSD',
      data: { price: '100', size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
    });

    expect(result.current.latestTrade).toBeNull();
    expect(result.current.trades).toEqual([]);
    // No tracked channel fired, so this frame never even committed.
    expect(result.current.lastMessageAt).toBeNull();
  });

  it('drops a ticker message when the ticker channel is disabled', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', {
        streamUrl: 'ws://test/ws/market',
        channels: { trades: false, ticker: false, orderBook: true },
      }),
    );
    act(() => latestSocket().triggerOpen());
    deliver({
      type: 'ticker',
      symbol: 'ETHUSD',
      data: {
        last_price: '1900',
        bid: '1899',
        ask: '1901',
        mark_price: '1900.5',
        price_change_24h: '3.2',
        event_time: '2026-01-01T00:00:00Z',
      },
    });

    expect(result.current.latestTicker).toBeNull();
  });

  it('still tracks the enabled order-book channel while trades/ticker are disabled', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', {
        streamUrl: 'ws://test/ws/market',
        channels: { trades: false, ticker: false, orderBook: true },
      }),
    );
    act(() => latestSocket().triggerOpen());
    deliver({
      type: 'orderbook',
      symbol: 'ETHUSD',
      data: {
        bids: [{ price: '100', size: '1' }],
        asks: [{ price: '101', size: '1' }],
        event_time: '2026-01-01T00:00:00Z',
        sequence: 1,
      },
    });

    expect(result.current.latestOrderBook?.bids).toEqual([{ price: '100', size: '1' }]);
    expect(result.current.lastMessageAt).not.toBeNull();
  });

  it('applies only the tracked fields of a snapshot, ignoring the rest', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', {
        streamUrl: 'ws://test/ws/market',
        channels: { trades: false, ticker: false, orderBook: true },
      }),
    );
    act(() => latestSocket().triggerOpen());
    deliver({
      type: 'snapshot',
      symbol: 'ETHUSD',
      trade: { price: '100', size: '1', side: 'buy', event_time: '2026-01-01T00:00:00Z' },
      ticker: {
        last_price: '1900',
        bid: '1899',
        ask: '1901',
        mark_price: '1900.5',
        price_change_24h: '3.2',
        event_time: '2026-01-01T00:00:00Z',
      },
      orderbook: {
        bids: [{ price: '99', size: '2' }],
        asks: [],
        event_time: '2026-01-01T00:00:00Z',
        sequence: 1,
      },
    });

    expect(result.current.latestTrade).toBeNull();
    expect(result.current.latestTicker).toBeNull();
    expect(result.current.latestOrderBook?.bids).toEqual([{ price: '99', size: '2' }]);
  });

  it('a pong still flushes and updates latency even with trades/ticker disabled', () => {
    const { result } = renderHook(() =>
      useMarketStream('ETHUSD', {
        streamUrl: 'ws://test/ws/market',
        channels: { trades: false, ticker: false, orderBook: true },
      }),
    );
    act(() => latestSocket().triggerOpen());
    act(() => vi.advanceTimersByTime(15_000)); // fires the heartbeat ping
    deliver({ type: 'pong' });

    expect(result.current.latencyMs).not.toBeNull();
  });
});
