import type { IndicatorParameterSpec } from '@/types/api/indicators';

/**
 * Common prediction-horizon values, offered as a quick-pick dropdown ahead
 * of a raw numeric input — most researchers reach for one of these rather
 * than an arbitrary integer, and a dropdown surfaces that vocabulary
 * instead of leaving every horizon choice as an unguided number field.
 */
export const HORIZON_PRESETS = [1, 2, 3, 5, 10, 20, 50] as const;

/** Sentinel `<select>` value for "type your own horizon", distinct from any real horizon value. */
export const CUSTOM_HORIZON_VALUE = '__custom__';

/** Which presets actually fit a given target's declared `horizon` parameter bounds. */
export function presetsInRange(minimum: number | null, maximum: number | null): number[] {
  return HORIZON_PRESETS.filter(
    (preset) => (minimum === null || preset >= minimum) && (maximum === null || preset <= maximum),
  );
}

export function isPresetValue(value: string, presets: readonly number[]): boolean {
  return presets.some((preset) => String(preset) === value);
}

/**
 * What the horizon `<select>` should show as selected: the value itself if
 * it matches an offered preset exactly, or the "Custom…" sentinel if it's
 * empty, unset, or a value outside the preset list.
 */
export function horizonSelectValue(value: string, presets: readonly number[]): string {
  return isPresetValue(value, presets) ? value : CUSTOM_HORIZON_VALUE;
}

export function horizonSpecFor(
  parameters: readonly IndicatorParameterSpec[],
): IndicatorParameterSpec | undefined {
  return parameters.find((parameter) => parameter.name === 'horizon');
}
