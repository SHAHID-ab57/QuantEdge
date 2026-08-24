import { describe, expect, it, vi } from 'vitest';
import type { Candle } from '@/types/api/market';
import { ReplayClock, type ReplayClockTick } from './replay-clock';

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

function tick(overrides: Partial<ReplayClockTick> = {}): ReplayClockTick {
  return {
    phase: 'playing',
    index: 0,
    candle: candle('2026-01-01T00:00:00Z'),
    timestampMs: Date.parse('2026-01-01T00:00:00Z'),
    speed: 1,
    isDiscontinuity: false,
    revealEpoch: 1,
    ...overrides,
  };
}

describe('ReplayClock', () => {
  it('starts with an idle, discontinuous initial snapshot before anything publishes', () => {
    const clock = new ReplayClock();
    const snapshot = clock.getSnapshot();
    expect(snapshot.phase).toBe('idle');
    expect(snapshot.candle).toBeNull();
    expect(snapshot.isDiscontinuity).toBe(true);
  });

  it('getSnapshot reflects the most recently published tick', () => {
    const clock = new ReplayClock();
    clock.publish(tick({ index: 3 }));
    expect(clock.getSnapshot().index).toBe(3);
  });

  it('notifies every subscriber on publish', () => {
    const clock = new ReplayClock();
    const a = vi.fn();
    const b = vi.fn();
    clock.subscribe(a);
    clock.subscribe(b);
    clock.publish(tick({ index: 5 }));
    expect(a).toHaveBeenCalledWith(expect.objectContaining({ index: 5 }));
    expect(b).toHaveBeenCalledWith(expect.objectContaining({ index: 5 }));
  });

  it('stops notifying a subscriber once it unsubscribes', () => {
    const clock = new ReplayClock();
    const listener = vi.fn();
    const unsubscribe = clock.subscribe(listener);
    clock.publish(tick({ index: 1 }));
    unsubscribe();
    clock.publish(tick({ index: 2 }));
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('isolates a throwing subscriber — the rest still get notified, and publish() itself never throws', () => {
    const clock = new ReplayClock();
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const throwing = vi.fn(() => {
      throw new Error('subscriber blew up');
    });
    const before = vi.fn();
    const after = vi.fn();
    clock.subscribe(before);
    clock.subscribe(throwing);
    clock.subscribe(after);

    expect(() => clock.publish(tick())).not.toThrow();

    expect(before).toHaveBeenCalledTimes(1);
    expect(throwing).toHaveBeenCalledTimes(1);
    expect(after).toHaveBeenCalledTimes(1); // notified despite an earlier subscriber throwing
    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    consoleErrorSpy.mockRestore();
  });

  it('supports multiple independent subscribers unsubscribing without affecting the others', () => {
    const clock = new ReplayClock();
    const kept = vi.fn();
    const removed = vi.fn();
    clock.subscribe(kept);
    const unsubscribeRemoved = clock.subscribe(removed);
    unsubscribeRemoved();
    clock.publish(tick());
    expect(kept).toHaveBeenCalledTimes(1);
    expect(removed).not.toHaveBeenCalled();
  });
});
