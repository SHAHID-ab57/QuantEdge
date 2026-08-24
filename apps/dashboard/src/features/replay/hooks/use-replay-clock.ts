'use client';

import { useSyncExternalStore } from 'react';
import type { ReplayClock, ReplayClockTick } from '../engine/replay-clock';

/**
 * Subscribes a component to a `ReplayClock`, returning its latest tick.
 * Built on `useSyncExternalStore` — the React-idiomatic way to read an
 * external store that publishes its own updates (as opposed to a plain
 * `useEffect` + local `useState` mirror, which can tear under concurrent
 * rendering) — rather than hand-rolled subscribe/unsubscribe wiring.
 *
 * This is the one function every future replay-synchronized module
 * (Trade Tape, Order Book, indicators, AI prediction playback, paper
 * trading, backtesting — see `extension-points.ts`) would call with the
 * same `engine.clock` instance `ReplayChart` already uses, guaranteeing
 * every consumer observes the exact same candle at the exact same moment
 * — there is no second code path that could drift out of sync with it.
 */
export function useReplayClockTick(clock: ReplayClock): ReplayClockTick {
  return useSyncExternalStore(clock.subscribe, clock.getSnapshot, clock.getSnapshot);
}
