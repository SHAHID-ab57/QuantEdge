/** Every supported playback multiplier, in ascending order. */
export const REPLAY_SPEEDS = [0.25, 0.5, 1, 2, 5, 10] as const;

export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

export const DEFAULT_REPLAY_SPEED: ReplaySpeed = 1;

/**
 * How long one candle stays on screen at 1x, before the speed multiplier is
 * applied. This is a playback-pacing constant, not an attempt to simulate
 * wall-clock-accurate market time — replaying 24 hours of 1-minute candles
 * at "1x" does not take 24 hours, the same way scrubbing through a video
 * doesn't. `BASE_TICK_MS` is deliberately independent of the candle's own
 * timeframe: a 1-minute candle and a 1-day candle both advance once per
 * `BASE_TICK_MS` at 1x, because what a researcher is controlling here is
 * "how fast am I stepping through this dataset," not "how fast is time
 * passing in the market." See `FRONTEND.md` § "Replay tick semantics" for
 * the full rationale.
 */
export const BASE_TICK_MS = 1_000;

export function isReplaySpeed(value: number): value is ReplaySpeed {
  return (REPLAY_SPEEDS as readonly number[]).includes(value);
}

/** Milliseconds between candle advances at `speed` — halves as speed doubles. */
export function tickIntervalMs(speed: ReplaySpeed): number {
  return BASE_TICK_MS / speed;
}

/** The next faster speed, or `speed` unchanged if already at the fastest — used by the `+` keyboard shortcut. */
export function fasterSpeed(speed: ReplaySpeed): ReplaySpeed {
  const index = REPLAY_SPEEDS.indexOf(speed);
  return REPLAY_SPEEDS[Math.min(index + 1, REPLAY_SPEEDS.length - 1)]!;
}

/** The next slower speed, or `speed` unchanged if already at the slowest — used by the `-` keyboard shortcut. */
export function slowerSpeed(speed: ReplaySpeed): ReplaySpeed {
  const index = REPLAY_SPEEDS.indexOf(speed);
  return REPLAY_SPEEDS[Math.max(index - 1, 0)]!;
}
