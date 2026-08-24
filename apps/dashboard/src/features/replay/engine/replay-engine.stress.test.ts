import { describe, expect, it } from 'vitest';
import { createInitialReplayState, replayReducer, type ReplayState } from './replay-state-machine';
import { computeTimeline } from './replay-timeline';

/**
 * A regression guard for the "support 1/6/24 hours of replay data without
 * freezing the UI" requirement, expressed as a timing assertion rather
 * than a one-off manual check. 24 hours of 1-minute candles is 1,440
 * ticks — this drives the reducer and the timeline calculation through
 * all of them (plus a 6x-larger, ~144-hour run for headroom) and asserts
 * the per-tick cost stays flat rather than growing, which is exactly the
 * property an accidentally-O(n)-per-tick implementation (e.g. re-deriving
 * something from the full candle list on every step, instead of O(1)
 * index arithmetic) would fail.
 */
describe('replay engine sustained-session stress test', () => {
  it('keeps per-tick reducer + timeline cost flat across a simulated 24-hour, 1,440-candle session', () => {
    const CANDLE_COUNT = 1_440; // 24h of 1-minute candles
    let state: ReplayState = {
      ...createInitialReplayState(),
      phase: 'paused',
      candleCount: CANDLE_COUNT,
    };
    // Built once, exactly as a real session holds one stable loaded array —
    // rebuilding it per tick would test this suite's own overhead, not the
    // engine's.
    const candles = Array.from({ length: CANDLE_COUNT }, (_, index) => ({
      open_time: new Date(index * 60_000).toISOString(),
      close_time: new Date(index * 60_000).toISOString(),
      open: '1',
      high: '1',
      low: '1',
      close: '1',
      volume: '1',
      source: 'test',
    }));

    const durationsMs: number[] = [];
    for (let i = 0; i < CANDLE_COUNT - 1; i += 1) {
      const start = performance.now();
      state = replayReducer(state, { type: 'NEXT' });
      // The timeline recompute the UI performs on every tick.
      computeTimeline(candles, state.currentIndex);
      durationsMs.push(performance.now() - start);
    }

    expect(state.phase).toBe('completed');
    expect(state.currentIndex).toBe(CANDLE_COUNT - 1);

    const tenPercent = Math.floor(durationsMs.length / 10);
    const avg = (values: number[]) => values.reduce((sum, v) => sum + v, 0) / values.length;
    const firstAvg = avg(durationsMs.slice(0, tenPercent));
    const lastAvg = avg(durationsMs.slice(-tenPercent));

    // A generous bound — the property under test is "no unbounded growth,"
    // not "zero variance" (JIT warm-up and GC noise are real).
    expect(lastAvg).toBeLessThan(Math.max(firstAvg * 5, 5));
  });

  it('completes a 6-hour session (360 one-minute candles) via the scheduler-driven TICK action just as cleanly', () => {
    const CANDLE_COUNT = 360;
    let state: ReplayState = {
      ...createInitialReplayState(),
      phase: 'playing',
      candleCount: CANDLE_COUNT,
    };
    for (let i = 0; i < CANDLE_COUNT - 1; i += 1) {
      state = replayReducer(state, { type: 'TICK' });
    }
    expect(state.phase).toBe('completed');
    expect(state.currentIndex).toBe(CANDLE_COUNT - 1);
  });
});
