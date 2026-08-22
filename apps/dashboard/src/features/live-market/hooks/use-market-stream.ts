'use client';

import { useEffect, useRef, useState } from 'react';
import { env } from '@/config/env';
import {
  MarketStreamMessageSchema,
  type LiveOrderBookData,
  type LiveTickerData,
  type LiveTradeData,
} from '@/types/api/market-stream';
import { deriveMarketStreamUrl } from '../lib/market-stream-url';

export type ConnectionState = 'connecting' | 'open' | 'reconnecting' | 'closed';

const DEFAULT_MAX_TRADES = 100;
const PING_INTERVAL_MS = 15_000;
const BASE_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;

export interface StreamChannels {
  trades?: boolean;
  ticker?: boolean;
  orderBook?: boolean;
}

const DEFAULT_CHANNELS: Required<StreamChannels> = {
  trades: true,
  ticker: true,
  orderBook: true,
};

export interface UseMarketStreamOptions {
  maxTrades?: number;
  /**
   * Which message types this instance actually tracks — everything is on
   * by default (the Live Market Dashboard needs all three). A frame for a
   * disabled channel is dropped before it touches the pending buffer *or*
   * schedules a commit, so a consumer that only cares about the order book
   * (the Order Book viewer) never re-renders on a trade or ticker tick it
   * would just discard anyway. `lastMessageAt` reflects the channels this
   * instance actually tracks, not literally every byte the socket
   * receives — a message that's skipped for being on a disabled channel
   * correctly never touches it, since flushing just to update a timestamp
   * nobody reads would be the very re-render this option exists to avoid.
   */
  channels?: StreamChannels;
  /** Overridable for tests; defaults to deriving from `NEXT_PUBLIC_API_URL`. */
  streamUrl?: string;
}

export interface UseMarketStreamResult {
  connectionState: ConnectionState;
  /** The symbol this data belongs to — never a stale one (see the filter below). */
  symbol: string | null;
  /** Epoch ms of the last message received (of any type), or `null` before the first one. */
  lastMessageAt: number | null;
  /** Epoch ms of the last *trade*, which is what the tape and forming candle track. */
  lastTradeAt: number | null;
  /** Consecutive reconnect attempts since the last successful connection. */
  reconnectAttempt: number;
  /** Round-trip time of the most recent heartbeat, or `null` before the first pong. */
  latencyMs: number | null;
  latestTrade: LiveTradeData | null;
  latestTicker: LiveTickerData | null;
  /** Newest first, capped at `maxTrades`. */
  trades: LiveTradeData[];
  /** Already sorted and depth-limited by the gateway — see `market-stream.ts`. */
  latestOrderBook: LiveOrderBookData | null;
}

interface StreamData {
  latestTrade: LiveTradeData | null;
  latestTicker: LiveTickerData | null;
  trades: LiveTradeData[];
  latestOrderBook: LiveOrderBookData | null;
  lastMessageAt: number | null;
  lastTradeAt: number | null;
  latencyMs: number | null;
}

const EMPTY_DATA: StreamData = {
  latestTrade: null,
  latestTicker: null,
  trades: [],
  latestOrderBook: null,
  lastMessageAt: null,
  lastTradeAt: null,
  latencyMs: null,
};

/** Mutable accumulator drained into React state once per flush. */
interface PendingUpdate {
  trades: LiveTradeData[];
  ticker: LiveTickerData | null;
  snapshotTrade: LiveTradeData | null;
  orderBook: LiveOrderBookData | null;
  lastMessageAt: number | null;
  lastTradeAt: number | null;
  latencyMs: number | null;
}

function emptyPending(): PendingUpdate {
  return {
    trades: [],
    ticker: null,
    snapshotTrade: null,
    orderBook: null,
    lastMessageAt: null,
    lastTradeAt: null,
    latencyMs: null,
  };
}

/**
 * Subscribes to live trade/ticker/order-book updates for one symbol over
 * the backend's market-stream gateway (`/api/v1/ws/market`) — never the
 * exchange directly. Reconnects with exponential backoff (capped at
 * `MAX_RECONNECT_DELAY_MS`) and re-subscribes on every (re)connect;
 * switching `symbol` tears down and reopens the connection.
 *
 * Incoming frames are buffered and committed at most once per animation
 * frame (`requestAnimationFrame`) rather than one `setState` per message —
 * a busy market can print many updates a second, and a commit per message
 * would re-render every consumer on every single one. rAF batching (over a
 * fixed timer) means a burst within one frame coalesces into the single
 * commit that frame can actually show, the commit lands right before the
 * browser's own paint so it can never land wastefully between frames, and
 * — for free — the whole pipeline pauses itself whenever the tab is
 * backgrounded, since browsers don't run rAF callbacks for hidden tabs.
 * Every frame is also checked against the requested symbol so a message
 * still in flight when the user switches markets can never be attributed
 * to the new one, and against `options.channels` (see there) so a
 * consumer that doesn't track a given message type pays nothing for it —
 * not a wasted array push, not a wasted commit.
 */
export function useMarketStream(
  symbol: string | null,
  options: UseMarketStreamOptions = {},
): UseMarketStreamResult {
  const maxTrades = options.maxTrades ?? DEFAULT_MAX_TRADES;
  const streamUrl = options.streamUrl ?? deriveMarketStreamUrl(env.NEXT_PUBLIC_API_URL);
  const channels = { ...DEFAULT_CHANNELS, ...options.channels };

  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [data, setData] = useState<StreamData>(EMPTY_DATA);
  const maxTradesRef = useRef(maxTrades);
  maxTradesRef.current = maxTrades;
  const channelsRef = useRef(channels);
  channelsRef.current = channels;

  useEffect(() => {
    if (!symbol) {
      setConnectionState('closed');
      setData(EMPTY_DATA);
      return undefined;
    }

    // Clear immediately on symbol change: showing the previous market's price
    // under the new market's name for even one frame would be a correctness
    // bug, not just a cosmetic one.
    setData(EMPTY_DATA);
    setReconnectAttempt(0);

    let cancelled = false;
    let attempt = 0;
    let socket: WebSocket | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let flushHandle: number | null = null;
    let pending = emptyPending();
    let pingSentAt: number | null = null;

    function flush() {
      flushHandle = null;
      if (cancelled) {
        return;
      }
      const update = pending;
      pending = emptyPending();
      setData((previous) => {
        const nextTrades =
          update.trades.length > 0
            ? [...update.trades].reverse().concat(previous.trades).slice(0, maxTradesRef.current)
            : previous.trades;
        return {
          // A streamed trade is always newer than a snapshot's trade, so the
          // snapshot only fills in when nothing has streamed yet.
          latestTrade: update.trades.at(-1) ?? update.snapshotTrade ?? previous.latestTrade,
          latestTicker: update.ticker ?? previous.latestTicker,
          trades: nextTrades,
          latestOrderBook: update.orderBook ?? previous.latestOrderBook,
          lastMessageAt: update.lastMessageAt ?? previous.lastMessageAt,
          lastTradeAt: update.lastTradeAt ?? previous.lastTradeAt,
          latencyMs: update.latencyMs ?? previous.latencyMs,
        };
      });
    }

    function scheduleFlush() {
      if (flushHandle === null) {
        flushHandle = requestAnimationFrame(flush);
      }
    }

    function clearTimers() {
      if (pingTimer !== null) {
        clearInterval(pingTimer);
        pingTimer = null;
      }
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (flushHandle !== null) {
        cancelAnimationFrame(flushHandle);
        flushHandle = null;
      }
    }

    function scheduleReconnect() {
      if (cancelled) {
        return;
      }
      attempt += 1;
      setReconnectAttempt(attempt);
      setConnectionState('reconnecting');
      const delay = Math.min(BASE_RECONNECT_DELAY_MS * 2 ** (attempt - 1), MAX_RECONNECT_DELAY_MS);
      reconnectTimer = setTimeout(connect, delay);
    }

    function handleMessage(raw: string) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return;
      }
      const result = MarketStreamMessageSchema.safeParse(parsed);
      if (!result.success) {
        return;
      }
      const message = result.data;
      const now = Date.now();
      pending.lastMessageAt = now;

      if (message.type === 'pong') {
        if (pingSentAt !== null) {
          pending.latencyMs = now - pingSentAt;
          pingSentAt = null;
        }
        scheduleFlush();
        return;
      }
      if (message.type === 'error') {
        scheduleFlush();
        return;
      }
      // Guards against a frame for a market the user has just switched away
      // from being folded into the new market's state.
      if (message.symbol !== symbol) {
        return;
      }
      const active = channelsRef.current;
      if (message.type === 'trade') {
        if (!active.trades) {
          return;
        }
        pending.trades.push(message.data);
        pending.lastTradeAt = now;
      } else if (message.type === 'ticker') {
        if (!active.ticker) {
          return;
        }
        pending.ticker = message.data;
      } else if (message.type === 'orderbook') {
        if (!active.orderBook) {
          return;
        }
        pending.orderBook = message.data;
      } else {
        let sawTrackedField = false;
        if (message.trade && active.trades) {
          pending.snapshotTrade = message.trade;
          sawTrackedField = true;
        }
        if (message.ticker && active.ticker) {
          pending.ticker = message.ticker;
          sawTrackedField = true;
        }
        if (message.orderbook && active.orderBook) {
          pending.orderBook = message.orderbook;
          sawTrackedField = true;
        }
        // A snapshot with only untracked fields (or none at all) has
        // nothing this instance needs to commit.
        if (!sawTrackedField) {
          return;
        }
      }
      scheduleFlush();
    }

    function connect() {
      if (cancelled) {
        return;
      }
      setConnectionState((previous) => (previous === 'reconnecting' ? previous : 'connecting'));
      const ws = new WebSocket(streamUrl);
      socket = ws;

      ws.onopen = () => {
        if (cancelled) {
          return;
        }
        attempt = 0;
        setReconnectAttempt(0);
        setConnectionState('open');
        ws.send(JSON.stringify({ action: 'subscribe', symbols: [symbol] }));
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            pingSentAt = Date.now();
            ws.send(JSON.stringify({ action: 'ping' }));
          }
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        if (cancelled) {
          return;
        }
        handleMessage(event.data);
      };

      ws.onclose = () => {
        if (pingTimer !== null) {
          clearInterval(pingTimer);
          pingTimer = null;
        }
        pingSentAt = null;
        socket = null;
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimers();
      socket?.close();
      socket = null;
    };
  }, [symbol, streamUrl]);

  return {
    connectionState,
    symbol,
    reconnectAttempt,
    lastMessageAt: data.lastMessageAt,
    lastTradeAt: data.lastTradeAt,
    latencyMs: data.latencyMs,
    latestTrade: data.latestTrade,
    latestTicker: data.latestTicker,
    trades: data.trades,
    latestOrderBook: data.latestOrderBook,
  };
}
