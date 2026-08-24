import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReplayClock, type ReplayClockTick } from '../engine/replay-clock';
import { useReplayClockTick } from './use-replay-clock';

function tick(overrides: Partial<ReplayClockTick> = {}): ReplayClockTick {
  return {
    phase: 'playing',
    index: 0,
    candle: null,
    timestampMs: null,
    speed: 1,
    isDiscontinuity: false,
    revealEpoch: 1,
    ...overrides,
  };
}

describe('useReplayClockTick', () => {
  it('returns the clock’s current snapshot on first render', () => {
    const clock = new ReplayClock();
    clock.publish(tick({ index: 7 }));
    const { result } = renderHook(() => useReplayClockTick(clock));
    expect(result.current.index).toBe(7);
  });

  it('re-renders the subscribed component when the clock publishes a new tick', () => {
    const clock = new ReplayClock();
    const { result } = renderHook(() => useReplayClockTick(clock));
    act(() => clock.publish(tick({ index: 3 })));
    expect(result.current.index).toBe(3);
  });

  it('unsubscribes on unmount — a publish afterward touches nothing', () => {
    const clock = new ReplayClock();
    const { unmount } = renderHook(() => useReplayClockTick(clock));
    unmount();
    expect(() => clock.publish(tick({ index: 9 }))).not.toThrow();
  });
});
