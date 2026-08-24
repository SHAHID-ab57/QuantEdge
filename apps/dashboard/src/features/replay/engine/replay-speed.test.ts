import { describe, expect, it } from 'vitest';
import {
  BASE_TICK_MS,
  fasterSpeed,
  isReplaySpeed,
  REPLAY_SPEEDS,
  slowerSpeed,
  tickIntervalMs,
} from './replay-speed';

describe('REPLAY_SPEEDS', () => {
  it('is sorted ascending and matches the six required multipliers', () => {
    expect(REPLAY_SPEEDS).toEqual([0.25, 0.5, 1, 2, 5, 10]);
    for (let i = 1; i < REPLAY_SPEEDS.length; i += 1) {
      expect(REPLAY_SPEEDS[i]!).toBeGreaterThan(REPLAY_SPEEDS[i - 1]!);
    }
  });
});

describe('isReplaySpeed', () => {
  it('accepts every defined speed', () => {
    for (const speed of REPLAY_SPEEDS) {
      expect(isReplaySpeed(speed)).toBe(true);
    }
  });

  it('rejects a value outside the defined set', () => {
    expect(isReplaySpeed(3)).toBe(false);
    expect(isReplaySpeed(0)).toBe(false);
  });
});

describe('tickIntervalMs', () => {
  it('returns the base interval at 1x', () => {
    expect(tickIntervalMs(1)).toBe(BASE_TICK_MS);
  });

  it('halves the interval as speed doubles', () => {
    expect(tickIntervalMs(2)).toBe(BASE_TICK_MS / 2);
    expect(tickIntervalMs(0.5)).toBe(BASE_TICK_MS * 2);
  });

  it('produces a strictly shorter interval for every faster speed, in order', () => {
    const intervals = REPLAY_SPEEDS.map(tickIntervalMs);
    for (let i = 1; i < intervals.length; i += 1) {
      expect(intervals[i]!).toBeLessThan(intervals[i - 1]!);
    }
  });
});

describe('fasterSpeed', () => {
  it('steps to the next entry in REPLAY_SPEEDS', () => {
    expect(fasterSpeed(1)).toBe(2);
    expect(fasterSpeed(0.25)).toBe(0.5);
  });

  it('stays at the fastest speed rather than going out of range', () => {
    expect(fasterSpeed(10)).toBe(10);
  });
});

describe('slowerSpeed', () => {
  it('steps to the previous entry in REPLAY_SPEEDS', () => {
    expect(slowerSpeed(1)).toBe(0.5);
    expect(slowerSpeed(10)).toBe(5);
  });

  it('stays at the slowest speed rather than going out of range', () => {
    expect(slowerSpeed(0.25)).toBe(0.25);
  });
});
