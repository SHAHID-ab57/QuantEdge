import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReplayScheduler } from './replay-scheduler';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ReplayScheduler', () => {
  it('is not running before start() is called', () => {
    const scheduler = new ReplayScheduler(1_000);
    expect(scheduler.isRunning).toBe(false);
  });

  it('calls the tick callback repeatedly at the configured interval', () => {
    const scheduler = new ReplayScheduler(1_000);
    const onTick = vi.fn();
    scheduler.start(onTick);

    expect(onTick).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1_000);
    expect(onTick).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1_000);
    expect(onTick).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(3_000);
    expect(onTick).toHaveBeenCalledTimes(5);
  });

  it('reports isRunning while started, and false again after stop()', () => {
    const scheduler = new ReplayScheduler(1_000);
    scheduler.start(vi.fn());
    expect(scheduler.isRunning).toBe(true);
    scheduler.stop();
    expect(scheduler.isRunning).toBe(false);
  });

  it('stops calling the callback once stop() is called', () => {
    const scheduler = new ReplayScheduler(1_000);
    const onTick = vi.fn();
    scheduler.start(onTick);
    vi.advanceTimersByTime(1_000);
    scheduler.stop();
    vi.advanceTimersByTime(10_000);
    expect(onTick).toHaveBeenCalledTimes(1);
  });

  it('is idempotent — calling start() twice does not create a second timer loop', () => {
    const scheduler = new ReplayScheduler(1_000);
    const onTick = vi.fn();
    scheduler.start(onTick);
    scheduler.start(vi.fn()); // second call should be ignored while already running
    vi.advanceTimersByTime(2_000);
    expect(onTick).toHaveBeenCalledTimes(2);
  });

  it('applies a new interval to subsequent ticks without resetting progress already made', () => {
    const scheduler = new ReplayScheduler(1_000);
    const onTick = vi.fn();
    scheduler.start(onTick);

    vi.advanceTimersByTime(1_000);
    expect(onTick).toHaveBeenCalledTimes(1);

    // Speed change: much shorter interval, applied to the *next* tick.
    scheduler.setIntervalMs(100);
    vi.advanceTimersByTime(100);
    expect(onTick).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(100);
    expect(onTick).toHaveBeenCalledTimes(3);
  });

  it('changing the interval mid-flight does not stop the scheduler', () => {
    const scheduler = new ReplayScheduler(1_000);
    scheduler.start(vi.fn());
    scheduler.setIntervalMs(50);
    expect(scheduler.isRunning).toBe(true);
  });

  it('can be restarted with a new callback after stopping', () => {
    const scheduler = new ReplayScheduler(1_000);
    const first = vi.fn();
    const second = vi.fn();
    scheduler.start(first);
    vi.advanceTimersByTime(1_000);
    scheduler.stop();
    scheduler.start(second);
    vi.advanceTimersByTime(1_000);
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('lets a tick callback stop the scheduler from inside itself without scheduling another tick', () => {
    const scheduler = new ReplayScheduler(1_000);
    const onTick = vi.fn(() => scheduler.stop());
    scheduler.start(onTick);
    vi.advanceTimersByTime(1_000);
    expect(onTick).toHaveBeenCalledTimes(1);
    expect(scheduler.isRunning).toBe(false);
    vi.advanceTimersByTime(10_000);
    expect(onTick).toHaveBeenCalledTimes(1);
  });
});
