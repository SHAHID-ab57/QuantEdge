/**
 * Drives the auto-advance timer behind "Play" — a small framework-agnostic
 * class (no React, no `useEffect`) so it can be unit-tested with fake
 * timers in isolation and reused unchanged from any host.
 *
 * Uses a self-rescheduling `setTimeout` rather than `setInterval`: changing
 * the interval mid-flight (`setSpeed`) takes effect on the *next* scheduled
 * tick without needing to tear down and recreate a running `setInterval`,
 * and a `setTimeout` chain can never let two ticks queue up back-to-back if
 * the host thread was briefly blocked, the way a fast `setInterval` can.
 */
export class ReplayScheduler {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private intervalMs: number;
  private onTick: (() => void) | null = null;

  constructor(initialIntervalMs: number) {
    this.intervalMs = initialIntervalMs;
  }

  get isRunning(): boolean {
    return this.timer !== null;
  }

  start(onTick: () => void): void {
    if (this.timer !== null) {
      return;
    }
    this.onTick = onTick;
    this.scheduleNext();
  }

  stop(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.onTick = null;
  }

  /**
   * Changes the interval. If a tick is already pending, it is rescheduled
   * to fire after the *new* interval, measured from now — so a speed
   * change is felt on the very next tick rather than only once the
   * already-in-flight (and now stale) wait finishes. This resets the
   * currently-pending wait rather than pro-rating the time already
   * elapsed toward it, which is a deliberate simplification: a replay
   * speed control is not a stopwatch, and the resulting timing error is at
   * most one interval, once, per speed change.
   */
  setIntervalMs(intervalMs: number): void {
    this.intervalMs = intervalMs;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
      this.scheduleNext();
    }
  }

  private scheduleNext(): void {
    this.timer = setTimeout(() => {
      this.timer = null;
      this.onTick?.();
      // Re-check `onTick`: the callback above may have called `stop()`
      // (e.g. replay just completed), in which case nothing should be
      // rescheduled.
      if (this.onTick !== null) {
        this.scheduleNext();
      }
    }, this.intervalMs);
  }
}
