import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Candle } from '@/types/api/market';
import { useReplayEngine, type ReplayDataStatus } from './use-replay-engine';

function candle(openTimeIso: string): Candle {
  return {
    open_time: openTimeIso,
    close_time: openTimeIso,
    open: '1',
    high: '1',
    low: '1',
    close: '1',
    volume: '1',
    source: 'test',
  };
}

const CANDLES: Candle[] = Array.from({ length: 5 }, (_, i) => candle(`2026-01-01T00:0${i}:00Z`));

function status(overrides: Partial<ReplayDataStatus> = {}): ReplayDataStatus {
  return {
    requestId: null,
    isLoading: false,
    isError: false,
    errorMessage: null,
    candles: undefined,
    ...overrides,
  };
}

function loadedStatus(requestId = 'req-1'): ReplayDataStatus {
  return status({ requestId, isLoading: false, candles: CANDLES });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useReplayEngine — loading lifecycle', () => {
  it('starts idle with nothing configured', () => {
    const { result } = renderHook(() => useReplayEngine(status()));
    expect(result.current.phase).toBe('idle');
  });

  it('moves to loading when a request begins, then paused once candles arrive', () => {
    const { result, rerender } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: status({ requestId: 'req-1', isLoading: true }),
    });
    expect(result.current.phase).toBe('loading');

    rerender(loadedStatus('req-1'));
    expect(result.current.phase).toBe('paused');
    expect(result.current.candleCount).toBe(5);
    expect(result.current.currentIndex).toBe(0);
  });

  it('moves to error when the request fails', () => {
    const { result, rerender } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: status({ requestId: 'req-1', isLoading: true }),
    });
    rerender(status({ requestId: 'req-1', isError: true, errorMessage: 'network down' }));
    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBe('network down');
  });

  it('moves to error for an empty result set (no candles for this configuration)', () => {
    const { result, rerender } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: status({ requestId: 'req-1', isLoading: true }),
    });
    rerender(status({ requestId: 'req-1', isLoading: false, candles: [] }));
    expect(result.current.phase).toBe('error');
  });

  it('resets and reloads when the request id changes (switching market/timeframe/range)', () => {
    const { result, rerender } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus('req-1'),
    });
    act(() => result.current.next());
    expect(result.current.currentIndex).toBe(1);

    rerender(status({ requestId: 'req-2', isLoading: true }));
    expect(result.current.phase).toBe('loading');
    expect(result.current.currentIndex).toBe(0);
  });
});

describe('useReplayEngine — controls', () => {
  function renderLoaded() {
    return renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
  }

  it('plays, advancing the current candle automatically on a timer', () => {
    const { result } = renderLoaded();
    act(() => result.current.play());
    expect(result.current.phase).toBe('playing');

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current.currentIndex).toBe(1);
  });

  it('pauses and stops the timer from advancing further', () => {
    const { result } = renderLoaded();
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(1_000));
    expect(result.current.currentIndex).toBe(1);

    act(() => result.current.pause());
    act(() => vi.advanceTimersByTime(5_000));
    expect(result.current.currentIndex).toBe(1);
    expect(result.current.phase).toBe('paused');
  });

  it('resumes from where it paused', () => {
    const { result } = renderLoaded();
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(1_000));
    act(() => result.current.pause());
    act(() => result.current.resume());
    expect(result.current.phase).toBe('playing');
    act(() => vi.advanceTimersByTime(1_000));
    expect(result.current.currentIndex).toBe(2);
  });

  it('stops and resets to the first candle', () => {
    const { result } = renderLoaded();
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(2_000));
    act(() => result.current.stop());
    expect(result.current.phase).toBe('paused');
    expect(result.current.currentIndex).toBe(0);
  });

  it('restarts from the first candle while preserving playback', () => {
    const { result } = renderLoaded();
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(2_000));
    act(() => result.current.restart());
    expect(result.current.phase).toBe('playing');
    expect(result.current.currentIndex).toBe(0);
    act(() => vi.advanceTimersByTime(1_000));
    expect(result.current.currentIndex).toBe(1);
  });

  it('steps forward and backward one candle at a time', () => {
    const { result } = renderLoaded();
    act(() => result.current.next());
    act(() => result.current.next());
    expect(result.current.currentIndex).toBe(2);
    act(() => result.current.previous());
    expect(result.current.currentIndex).toBe(1);
  });

  it('completes automatically once the last candle is reached during playback', () => {
    const { result } = renderLoaded();
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(4_000));
    expect(result.current.currentIndex).toBe(4);
    expect(result.current.phase).toBe('completed');
    // No further ticks should be scheduled once completed.
    act(() => vi.advanceTimersByTime(5_000));
    expect(result.current.currentIndex).toBe(4);
  });
});

describe('useReplayEngine — speed', () => {
  it('changes tick cadence without resetting the current index', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.next()); // index 1
    act(() => result.current.play());
    act(() => result.current.setSpeed(10));
    expect(result.current.currentIndex).toBe(1); // unaffected by the speed change itself

    act(() => vi.advanceTimersByTime(100)); // 1000ms / 10x = 100ms
    expect(result.current.currentIndex).toBe(2);
  });
});

describe('useReplayEngine — seeking', () => {
  it('seeks directly to an index while paused', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.seekToIndex(3));
    expect(result.current.currentIndex).toBe(3);
    expect(result.current.phase).toBe('paused');
  });

  it('resumes playback after a seek performed mid-playback', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.play());
    act(() => result.current.seekToIndex(2));
    expect(result.current.phase).toBe('playing');
    act(() => vi.advanceTimersByTime(1_000));
    expect(result.current.currentIndex).toBe(3);
  });

  it('seeks by progress percentage', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.seekToProgress(100));
    expect(result.current.currentIndex).toBe(4);
  });
});

describe('useReplayEngine — clock synchronization', () => {
  it('exposes the same clock instance across renders', () => {
    const { result, rerender } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    const first = result.current.clock;
    rerender(loadedStatus());
    expect(result.current.clock).toBe(first);
  });

  it('publishes a tick reflecting the current candle whenever the index advances', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.next());
    const snapshot = result.current.clock.getSnapshot();
    expect(snapshot.index).toBe(1);
    expect(snapshot.candle).toBe(result.current.currentCandle);
    expect(snapshot.phase).toBe('paused');
  });

  it('marks a forward step as not discontinuous', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.next()); // first tick after load is discontinuous (a fresh load)
    act(() => result.current.next()); // this one is a plain forward step
    expect(result.current.clock.getSnapshot().isDiscontinuity).toBe(false);
  });

  it('marks a seek as discontinuous', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.next());
    act(() => result.current.seekToIndex(3));
    expect(result.current.clock.getSnapshot().isDiscontinuity).toBe(true);
    expect(result.current.clock.getSnapshot().index).toBe(3);
  });

  it('notifies a live subscriber on every tick during auto-play, not just on read', () => {
    const { result } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    const listener = vi.fn();
    result.current.clock.subscribe(listener);
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(2_000));
    expect(listener.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(listener.mock.calls.at(-1)?.[0].index).toBe(result.current.currentIndex);
  });
});

describe('useReplayEngine — cleanup', () => {
  it('stops the scheduler on unmount so no tick fires afterward', () => {
    const { result, unmount } = renderHook((props: ReplayDataStatus) => useReplayEngine(props), {
      initialProps: loadedStatus(),
    });
    act(() => result.current.play());
    unmount();
    // Nothing to assert against `result.current` post-unmount, but a
    // dangling timer would throw "Cannot update state on an unmounted
    // component" (a React warning surfaced as a thrown error in strict
    // test setups) once it fires — this simply must not happen.
    expect(() => vi.advanceTimersByTime(10_000)).not.toThrow();
  });
});
