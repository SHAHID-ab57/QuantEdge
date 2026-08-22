'use client';

import { useEffect, useRef, useState } from 'react';
import { env } from '@/config/env';
import {
  MarketStreamMessageSchema,
  type LiveTickerData,
  type LiveTradeData,
} from '@/types/api/market-stream';
import { deriveMarketStreamUrl } from '../lib/market-stream-url';

export type ConnectionState = 'connecting' | 'open' | 'reconnecting' | 'closed';

const DEFAULT_MAX_TRADES = 100;
const PING_INTERVAL_MS = 15_000;
const BASE_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;

/**
 * How often buffered stream updates are committed to React state. A busy
 * market can print many trades per second, and one `setState` per frame
 * would re-render the price card, chart and tape on every single print.
 * Coalescing into ~10 commits/second keeps the UI responsive under bursts
 * while staying far below the threshold where a human perceives lag.
 */
const FLUSH_INTERVAL_MS = 100;

export interface UseMarketStreamOptions {
  maxTrades?: number;
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
}

interface StreamData {
  latestTrade: LiveTradeData | null;
  latestTicker: LiveTickerData | null;
  trades: LiveTradeData[];
  lastMessageAt: number | null;
  lastTradeAt: number | null;
  latencyMs: number | null;
}

const EMPTY_DATA: StreamData = {
  latestTrade: null,
  latestTicker: null,
  trades: [],
  lastMessageAt: null,
  lastTradeAt: null,
  latencyMs: null,
};

/** Mutable accumulator drained into React state once per flush. */
interface PendingUpdate {
  trades: LiveTradeData[];
  ticker: LiveTickerData | null;
  snapshotTrade: LiveTradeData | null;
  lastMessageAt: number | null;
  lastTradeAt: number | null;
  latencyMs: number | null;
}

function emptyPending(): PendingUpdate {
  return {
    trades: [],
    ticker: null,
    snapshotTrade: null,
    lastMessageAt: null,
    lastTradeAt: null,
    latencyMs: null,
  };
}

/**
 * Subscribes to live trade/ticker updates for one symbol over the
 * backend's market-stream gateway (`/api/v1/ws/market`) — never the
 * exchange directly. Reconnects with exponential backoff (capped at
 * `MAX_RECONNECT_DELAY_MS`) and re-subscribes on every (re)connect;
 * switching `symbol` tears down and reopens the connection.
 *
 * Incoming frames are buffered and committed on a fixed interval rather
 * than one-state-update-per-message (see `FLUSH_INTERVAL_MS`), and every
 * frame is checked against the requested symbol so a message still in
 * flight when the user switches markets can never be attributed to the new
 * one.
 */
export function useMarketStream(
  symbol: string | null,
  options: UseMarketStreamOptions = {},
): UseMarketStreamResult {
  const maxTrades = options.maxTrades ?? DEFAULT_MAX_TRADES;
  const streamUrl = options.streamUrl ?? deriveMarketStreamUrl(env.NEXT_PUBLIC_API_URL);

  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [data, setData] = useState<StreamData>(EMPTY_DATA);
  const maxTradesRef = useRef(maxTrades);
  maxTradesRef.current = maxTrades;

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
    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    let pending = emptyPending();
    let pingSentAt: number | null = null;

    function flush() {
      flushTimer = null;
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
          lastMessageAt: update.lastMessageAt ?? previous.lastMessageAt,
          lastTradeAt: update.lastTradeAt ?? previous.lastTradeAt,
          latencyMs: update.latencyMs ?? previous.latencyMs,
        };
      });
    }

    function scheduleFlush() {
      if (flushTimer === null) {
        flushTimer = setTimeout(flush, FLUSH_INTERVAL_MS);
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
      if (flushTimer !== null) {
        clearTimeout(flushTimer);
        flushTimer = null;
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
      if (message.type === 'trade') {
        pending.trades.push(message.data);
        pending.lastTradeAt = now;
      } else if (message.type === 'ticker') {
        pending.ticker = message.data;
      } else {
        if (message.trade) {
          pending.snapshotTrade = message.trade;
        }
        if (message.ticker) {
          pending.ticker = message.ticker;
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
  };
}
