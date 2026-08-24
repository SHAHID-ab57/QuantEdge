'use client';

import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import type { Candle } from '@/types/api/market';
import { ReplayClock } from '../engine/replay-clock';
import { ReplayScheduler } from '../engine/replay-scheduler';
import { isReplaySpeed, tickIntervalMs, type ReplaySpeed } from '../engine/replay-speed';
import {
  createInitialReplayState,
  replayReducer,
  type ReplayPhase,
} from '../engine/replay-state-machine';
import { computeTimeline, indexForProgress, type ReplayTimeline } from '../engine/replay-timeline';

/** The externally-driven data status this hook translates into replay phases — see `useReplayCandles`. */
export interface ReplayDataStatus {
  /** A value that changes once per distinct load attempt (e.g. a query key) — `null` when nothing is configured yet. */
  requestId: string | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  candles: Candle[] | undefined;
}

export interface UseReplayEngineResult {
  phase: ReplayPhase;
  currentIndex: number;
  currentCandle: Candle | null;
  /** The full loaded set — stable until the next successful load. */
  candles: Candle[];
  candleCount: number;
  speed: ReplaySpeed;
  error: string | null;
  /** See `ReplayState.revealEpoch` — bumps on every discontinuous jump, for chart-sync consumers. */
  revealEpoch: number;
  timeline: ReplayTimeline;
  /**
   * The centralized synchronization primitive — see `engine/replay-clock.ts`.
   * `ReplayChart` reads it via `useReplayClockTick`; any future replay-
   * synchronized module (Trade Tape, Order Book, indicators, AI prediction
   * playback, paper trading, backtesting) would subscribe to this exact
   * same instance rather than deriving its own position from `currentIndex`/
   * `revealEpoch` independently.
   */
  clock: ReplayClock;
  play: () => void;
  resume: () => void;
  pause: () => void;
  stop: () => void;
  restart: () => void;
  next: () => void;
  previous: () => void;
  seekToIndex: (index: number) => void;
  seekToProgress: (percent: number) => void;
  setSpeed: (speed: ReplaySpeed) => void;
}

/**
 * The React-facing side of the replay engine: a `useReducer` around the
 * pure `replayReducer` (`engine/replay-state-machine.ts`) plus one
 * `ReplayScheduler` instance (`engine/replay-scheduler.ts`) kept alive in a
 * ref across renders. Every rule about *whether* a transition is valid
 * lives in the reducer, already exhaustively unit-tested with no React
 * involved; this hook's only two jobs are (1) translating `status` — an
 * external, already-resolved data-fetch result — into `LOAD_*` actions,
 * and (2) starting/stopping the scheduler in lockstep with `phase`.
 *
 * `status.requestId` is what tells this hook "a new load attempt has
 * begun" — it's expected to change (e.g. a new query key) exactly once per
 * distinct replay configuration. Because `LOAD_SUCCESS`/`LOAD_ERROR` only
 * ever apply while the reducer's own phase is `'loading'` (see the reducer's
 * own guards), a `status` that re-renders this hook multiple times while
 * settling is harmless — every dispatch after the first is a no-op.
 */
export function useReplayEngine(status: ReplayDataStatus): UseReplayEngineResult {
  const [state, dispatch] = useReducer(replayReducer, undefined, createInitialReplayState);
  const candlesRef = useRef<Candle[]>([]);
  const schedulerRef = useRef<ReplayScheduler | null>(null);
  if (schedulerRef.current === null) {
    schedulerRef.current = new ReplayScheduler(tickIntervalMs(state.speed));
  }
  const clockRef = useRef<ReplayClock | null>(null);
  if (clockRef.current === null) {
    clockRef.current = new ReplayClock();
  }
  const lastPublishedEpochRef = useRef<number>(-1);

  const requestIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (status.requestId === requestIdRef.current) {
      return;
    }
    requestIdRef.current = status.requestId;
    if (status.requestId !== null) {
      candlesRef.current = [];
      dispatch({ type: 'LOAD_START' });
    }
  }, [status.requestId]);

  useEffect(() => {
    if (requestIdRef.current === null) {
      return;
    }
    if (status.isError) {
      dispatch({
        type: 'LOAD_ERROR',
        message: status.errorMessage ?? 'Failed to load replay data.',
      });
    } else if (!status.isLoading && status.candles) {
      candlesRef.current = status.candles;
      dispatch({ type: 'LOAD_SUCCESS', candleCount: status.candles.length });
    }
  }, [status.isLoading, status.isError, status.errorMessage, status.candles]);

  // Starts/stops the auto-advance timer in lockstep with `phase` — never
  // runs while paused/seeking/completed/error, and its cleanup guarantees
  // nothing keeps ticking after this hook unmounts.
  useEffect(() => {
    const scheduler = schedulerRef.current!;
    if (state.phase === 'playing') {
      scheduler.start(() => dispatch({ type: 'TICK' }));
    } else {
      scheduler.stop();
    }
    return () => scheduler.stop();
  }, [state.phase]);

  // A speed change reschedules the *interval*, never the reducer state —
  // this is what satisfies "changing speed should not restart replay."
  useEffect(() => {
    schedulerRef.current!.setIntervalMs(tickIntervalMs(state.speed));
  }, [state.speed]);

  // Broadcasts every state change relevant to synchronization through the
  // centralized clock — see `engine/replay-clock.ts`. This is the *only*
  // place anything publishes to it; the reducer above remains the sole
  // source of truth, and this effect is purely a fan-out of its result.
  useEffect(() => {
    const candle = candlesRef.current[state.currentIndex] ?? null;
    const isDiscontinuity = state.revealEpoch !== lastPublishedEpochRef.current;
    lastPublishedEpochRef.current = state.revealEpoch;
    clockRef.current!.publish({
      phase: state.phase,
      index: state.currentIndex,
      candle,
      timestampMs: candle ? Date.parse(candle.open_time) : null,
      speed: state.speed,
      isDiscontinuity,
      revealEpoch: state.revealEpoch,
    });
    // candlesRef.current is read fresh above; candleCount changes exactly
    // when the ref does, so it's the correct proxy dependency (same
    // pattern as currentCandle/timeline below) — every other value read
    // in this effect is already listed explicitly.
  }, [state.phase, state.currentIndex, state.candleCount, state.speed, state.revealEpoch]);

  const wasPlayingRef = useRef(false);
  wasPlayingRef.current = state.phase === 'playing';

  const play = useCallback(() => dispatch({ type: 'PLAY' }), []);
  const resume = useCallback(() => dispatch({ type: 'RESUME' }), []);
  const pause = useCallback(() => dispatch({ type: 'PAUSE' }), []);
  const stop = useCallback(() => dispatch({ type: 'STOP' }), []);
  const restart = useCallback(() => dispatch({ type: 'RESTART' }), []);
  const next = useCallback(() => dispatch({ type: 'NEXT' }), []);
  const previous = useCallback(() => dispatch({ type: 'PREVIOUS' }), []);

  const seekToIndex = useCallback((index: number) => {
    const resumeToPlaying = wasPlayingRef.current;
    dispatch({ type: 'SEEK_START' });
    dispatch({ type: 'SEEK_COMPLETE', index, resumeToPlaying });
  }, []);

  const seekToProgress = useCallback((percent: number) => {
    const index = indexForProgress(candlesRef.current, percent);
    const resumeToPlaying = wasPlayingRef.current;
    dispatch({ type: 'SEEK_START' });
    dispatch({ type: 'SEEK_COMPLETE', index, resumeToPlaying });
  }, []);

  const setSpeed = useCallback((speed: ReplaySpeed) => {
    if (isReplaySpeed(speed)) {
      dispatch({ type: 'SET_SPEED', speed });
    }
  }, []);

  const currentCandle = useMemo(
    () => candlesRef.current[state.currentIndex] ?? null,
    // eslint-disable-next-line react-hooks/exhaustive-deps -- candlesRef.current is read fresh; candleCount changes exactly when the ref does.
    [state.currentIndex, state.candleCount],
  );

  const timeline = useMemo(
    () => computeTimeline(candlesRef.current, state.currentIndex),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- candlesRef.current is read fresh; candleCount changes exactly when the ref does.
    [state.currentIndex, state.candleCount],
  );

  return {
    phase: state.phase,
    currentIndex: state.currentIndex,
    currentCandle,
    candles: candlesRef.current,
    candleCount: state.candleCount,
    speed: state.speed,
    error: state.error,
    revealEpoch: state.revealEpoch,
    timeline,
    clock: clockRef.current,
    play,
    resume,
    pause,
    stop,
    restart,
    next,
    previous,
    seekToIndex,
    seekToProgress,
    setSpeed,
  };
}
