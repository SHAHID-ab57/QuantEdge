import type { Candle } from '@/types/api/market';
import type { ReplayPhase } from './replay-state-machine';

/**
 * One synchronized snapshot of "where replay is right now" — the single
 * payload every module that needs to stay in lockstep with replay
 * consumes, instead of each deriving its own notion of position from raw
 * engine fields. `ReplayChart` is the first real consumer
 * (`hooks/use-replay-chart-sync.ts` now sources its three inputs from a
 * tick rather than being handed `candles`/`currentIndex`/`revealEpoch`
 * directly by the page); a future Trade Tape/Order Book/indicator/AI/
 * paper-trading/backtesting module would subscribe to the exact same
 * `ReplayClock` and receive the exact same tick — see `extension-points.ts`.
 */
export interface ReplayClockTick {
  phase: ReplayPhase;
  index: number;
  candle: Candle | null;
  /** `candle.open_time` as epoch ms, or `null` before anything is loaded. */
  timestampMs: number | null;
  speed: number;
  /**
   * `true` when this tick represents a discontinuous jump (seek, previous,
   * restart, stop) rather than a plain forward advance — mirrors
   * `ReplayState.revealEpoch` bumping, carried through so a subscriber
   * never has to look at the reducer's internals directly.
   */
  isDiscontinuity: boolean;
  revealEpoch: number;
}

const INITIAL_TICK: ReplayClockTick = {
  phase: 'idle',
  index: 0,
  candle: null,
  timestampMs: null,
  speed: 1,
  isDiscontinuity: true,
  revealEpoch: 0,
};

export type ReplayClockListener = (tick: ReplayClockTick) => void;

/**
 * The centralized clock every replay-synchronized module reads from.
 * Deliberately framework-agnostic (no React import) and deliberately not
 * itself the source of truth for replay state — `replayReducer`
 * (`replay-state-machine.ts`) still owns that; `useReplayEngine` merely
 * *broadcasts* each resulting state as one `ReplayClockTick` through this
 * class after every dispatch. This mirrors the backend's own broker-free
 * in-process `EventBus` (`services/api/app/events/bus.py`) — a single
 * publisher, many independent subscribers, no subscriber able to block or
 * affect another — applied client-side to the one thing every replay
 * consumer needs to agree on: "what candle are we looking at right now."
 *
 * Exposes a `getSnapshot`/`subscribe` pair compatible with React's
 * `useSyncExternalStore` (see `hooks/use-replay-clock.ts`) rather than a
 * bare event-emitter, so a consumer always has a current value to read —
 * including before it has ever subscribed, and correctly under concurrent
 * rendering.
 */
export class ReplayClock {
  private tick: ReplayClockTick = INITIAL_TICK;
  private readonly listeners = new Set<ReplayClockListener>();

  getSnapshot = (): ReplayClockTick => this.tick;

  subscribe = (listener: ReplayClockListener): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /**
   * A listener that throws is isolated — logged, never allowed to stop the
   * remaining subscribers from being notified — the same guarantee the
   * backend's `EventBus` gives its own handlers, applied here without that
   * bus's `asyncio.Task`-per-handler mechanism (this runs synchronously on
   * the caller's stack, so isolation is a try/catch per listener instead).
   */
  publish(tick: ReplayClockTick): void {
    this.tick = tick;
    for (const listener of this.listeners) {
      try {
        listener(tick);
      } catch (error) {
        // A subscriber's bug must never silently disappear, but it also
        // must never stop this synchronous fan-out from reaching the
        // remaining subscribers.
        // eslint-disable-next-line no-console
        console.error('ReplayClock listener threw; other subscribers were still notified.', error);
      }
    }
  }
}
