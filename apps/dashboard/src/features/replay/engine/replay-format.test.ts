import { describe, expect, it } from 'vitest';
import { estimateCompletionMs, formatDuration } from './replay-format';

describe('formatDuration', () => {
  it('shows an em dash for null, negative, or non-finite durations', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(-1)).toBe('—');
    expect(formatDuration(Number.NaN)).toBe('—');
  });

  it('formats seconds only under a minute', () => {
    expect(formatDuration(45_000)).toBe('45s');
    expect(formatDuration(0)).toBe('0s');
  });

  it('formats minutes and seconds under an hour', () => {
    expect(formatDuration(150_000)).toBe('2m 30s');
  });

  it('formats hours and minutes at an hour or beyond, dropping seconds', () => {
    expect(formatDuration(3_600_000)).toBe('1h 0m');
    expect(formatDuration(3_600_000 + 15 * 60_000)).toBe('1h 15m');
  });

  it('rounds to the nearest second', () => {
    expect(formatDuration(999)).toBe('1s');
  });
});

describe('estimateCompletionMs', () => {
  it('is zero once there are no candles remaining', () => {
    expect(estimateCompletionMs(0, 1_000)).toBe(0);
    expect(estimateCompletionMs(-1, 1_000)).toBe(0);
  });

  it('multiplies remaining candles by the tick interval', () => {
    expect(estimateCompletionMs(10, 1_000)).toBe(10_000);
  });

  it('scales down at higher speeds (a shorter tick interval)', () => {
    expect(estimateCompletionMs(100, 100)).toBe(10_000);
  });
});
