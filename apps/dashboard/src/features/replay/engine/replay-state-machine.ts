import { clampIndex } from './replay-timeline';
import { DEFAULT_REPLAY_SPEED, type ReplaySpeed } from './replay-speed';

/**
 * The seven states this dashboard's replay controls can be in. `seeking` is
 * genuinely transient — see `ReplayAction`'s `SEEK_START`/`SEEK_COMPLETE`
 * pair below for why it is still a real, dispatched state rather than a
 * cosmetic label.
 */
export type ReplayPhase =
  'idle' | 'loading' | 'playing' | 'paused' | 'seeking' | 'completed' | 'error';

export interface ReplayState {
  phase: ReplayPhase;
  /** Position within the loaded candle set. Always `0` when nothing is loaded. */
  currentIndex: number;
  candleCount: number;
  speed: ReplaySpeed;
  error: string | null;
  /**
   * Bumped on every *discontinuous* jump — seek, previous, restart, stop —
   * and left untouched by a plain forward `NEXT`/`TICK`. This is the signal
   * the chart-sync layer (`hooks/use-replay-chart-sync.ts`) uses to decide
   * whether it can push the new candle incrementally via
   * `CandlestickChart`'s `liveCandle` prop, or must reseed the whole series:
   * lightweight-charts' `series.update()` can only append a bar newer than
   * everything already drawn (exactly what a forward step does) or replace
   * the single most recent one — it cannot "un-draw" history, which any
   * backward or jump move would require.
   */
  revealEpoch: number;
}

export type ReplayAction =
  | { type: 'LOAD_START' }
  | { type: 'LOAD_SUCCESS'; candleCount: number }
  | { type: 'LOAD_ERROR'; message: string }
  | { type: 'PLAY' }
  | { type: 'RESUME' }
  | { type: 'PAUSE' }
  | { type: 'STOP' }
  | { type: 'RESTART' }
  | { type: 'NEXT' }
  | { type: 'PREVIOUS' }
  | { type: 'TICK' }
  /** Dispatched first by a seek, always followed synchronously by `SEEK_COMPLETE`. */
  | { type: 'SEEK_START' }
  | { type: 'SEEK_COMPLETE'; index: number; resumeToPlaying: boolean }
  | { type: 'SET_SPEED'; speed: ReplaySpeed };

export function createInitialReplayState(): ReplayState {
  return {
    phase: 'idle',
    currentIndex: 0,
    candleCount: 0,
    speed: DEFAULT_REPLAY_SPEED,
    error: null,
    revealEpoch: 0,
  };
}

/** Advances `state.currentIndex` by one, clamped to the last candle, completing replay on arrival. */
function advance(state: ReplayState): ReplayState {
  const nextIndex = clampIndex(state.currentIndex + 1, state.candleCount);
  const reachedEnd = nextIndex >= state.candleCount - 1;
  return {
    ...state,
    currentIndex: nextIndex,
    phase: reachedEnd ? 'completed' : state.phase,
  };
}

/**
 * A pure reducer over the seven replay phases — no timers, no React, no
 * data fetching. `useReplayEngine` (the only place this is called from) is
 * a thin `useReducer` wrapper plus a scheduler for auto-advancing while
 * `playing`; every actual rule about which transition is valid from which
 * phase lives here, where it can be exhaustively unit-tested without
 * mounting a component. An action that doesn't apply to the current phase
 * (e.g. `PAUSE` while `idle`) is a no-op — it returns `state` unchanged
 * rather than throwing, since a disabled button that still fires an event
 * (a stray keyboard shortcut, a race between a click and a phase change)
 * should never crash a research session.
 */
export function replayReducer(state: ReplayState, action: ReplayAction): ReplayState {
  switch (action.type) {
    case 'LOAD_START':
      return {
        ...createInitialReplayState(),
        speed: state.speed,
        phase: 'loading',
      };

    case 'LOAD_SUCCESS':
      // Also accepted from 'error': a retry after a failed (or empty) load
      // reuses the same request id — see `useReplayEngine` — rather than
      // going through another `LOAD_START`, so this is the only phase
      // transition a successful retry has to land on.
      if (state.phase !== 'loading' && state.phase !== 'error') {
        return state;
      }
      return {
        ...state,
        phase: action.candleCount > 0 ? 'paused' : 'error',
        candleCount: action.candleCount,
        currentIndex: 0,
        error: action.candleCount > 0 ? null : 'No candles were found for this configuration.',
        revealEpoch: state.revealEpoch + 1,
      };

    case 'LOAD_ERROR':
      if (state.phase !== 'loading' && state.phase !== 'error') {
        return state;
      }
      return { ...state, phase: 'error', error: action.message };

    case 'PLAY':
      if (state.phase !== 'paused' && state.phase !== 'completed') {
        return state;
      }
      return {
        ...state,
        phase: 'playing',
        currentIndex: state.phase === 'completed' ? 0 : state.currentIndex,
        revealEpoch: state.phase === 'completed' ? state.revealEpoch + 1 : state.revealEpoch,
      };

    case 'RESUME':
      if (state.phase !== 'paused') {
        return state;
      }
      return { ...state, phase: 'playing' };

    case 'PAUSE':
      if (state.phase !== 'playing') {
        return state;
      }
      return { ...state, phase: 'paused' };

    case 'STOP':
      if (state.phase !== 'playing' && state.phase !== 'paused' && state.phase !== 'completed') {
        return state;
      }
      return { ...state, phase: 'paused', currentIndex: 0, revealEpoch: state.revealEpoch + 1 };

    case 'RESTART':
      if (state.phase !== 'playing' && state.phase !== 'paused' && state.phase !== 'completed') {
        return state;
      }
      return {
        ...state,
        phase: state.phase === 'completed' ? 'paused' : state.phase,
        currentIndex: 0,
        revealEpoch: state.revealEpoch + 1,
      };

    case 'NEXT':
      if (state.phase !== 'paused' && state.phase !== 'completed' && state.phase !== 'playing') {
        return state;
      }
      if (state.candleCount === 0) {
        return state;
      }
      return advance(state);

    case 'TICK':
      if (state.phase !== 'playing') {
        return state;
      }
      return advance(state);

    case 'PREVIOUS':
      if (state.phase !== 'paused' && state.phase !== 'completed') {
        return state;
      }
      if (state.currentIndex === 0) {
        return state;
      }
      return {
        ...state,
        phase: 'paused',
        currentIndex: clampIndex(state.currentIndex - 1, state.candleCount),
        revealEpoch: state.revealEpoch + 1,
      };

    case 'SEEK_START':
      if (state.candleCount === 0) {
        return state;
      }
      return { ...state, phase: 'seeking' };

    case 'SEEK_COMPLETE': {
      if (state.phase !== 'seeking') {
        return state;
      }
      const targetIndex = clampIndex(action.index, state.candleCount);
      // Landing exactly on the last candle leaves nothing further to
      // advance to — the same "nothing left" state a forward NEXT/TICK
      // would reach, regardless of whether the seek intended to resume
      // playback afterward.
      const atEnd = targetIndex >= state.candleCount - 1;
      let resolvedPhase: ReplayPhase = 'paused';
      if (atEnd) {
        resolvedPhase = 'completed';
      } else if (action.resumeToPlaying) {
        resolvedPhase = 'playing';
      }
      return {
        ...state,
        phase: resolvedPhase,
        currentIndex: targetIndex,
        revealEpoch: state.revealEpoch + 1,
      };
    }

    case 'SET_SPEED':
      return { ...state, speed: action.speed };

    default:
      return state;
  }
}
