import type { IndicatorParameterSpec } from '@/types/api/indicators';

/** Form state is kept as strings — that is what an `<input>` holds and what the query string sends. */
export type ParameterValues = Record<string, string>;

/**
 * Seed a form from the backend's published defaults.
 *
 * A required parameter (one with no default) seeds to an empty string so
 * it renders as a blank, obviously-unfilled field rather than a
 * plausible-looking zero the researcher might not notice they never chose.
 */
export function defaultValuesFor(specs: readonly IndicatorParameterSpec[]): ParameterValues {
  const values: ParameterValues = {};
  for (const spec of specs) {
    values[spec.name] =
      spec.default === null || spec.default === undefined ? '' : String(spec.default);
  }
  return values;
}

/**
 * Drop empty values before sending.
 *
 * An omitted optional parameter must reach the backend as *absent*, not as
 * an empty string: the backend applies the declared default for a missing
 * key, but would reject `""` as an invalid int. Sending nothing is what
 * gets the documented default behaviour.
 */
export function toRequestParams(values: ParameterValues): Record<string, string> {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value.trim() !== ''));
}

/**
 * Client-side validation mirroring the backend's own parameter rules, so a
 * researcher gets an immediate, field-anchored message instead of a
 * round-trip.
 *
 * This is a convenience, never the enforcement boundary — the backend
 * revalidates everything (see `validate_parameters`), because a UI check
 * is trivially bypassed and duplicated rules drift. Returns a map of
 * parameter name → message; empty means "nothing obviously wrong".
 */
export function validateValues(
  specs: readonly IndicatorParameterSpec[],
  values: ParameterValues,
): Record<string, string> {
  const errors: Record<string, string> = {};

  for (const spec of specs) {
    const raw = (values[spec.name] ?? '').trim();

    if (raw === '') {
      if (spec.required) {
        errors[spec.name] = 'Required';
      }
      continue;
    }

    if (spec.type === 'int' || spec.type === 'float') {
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) {
        errors[spec.name] = `Must be a ${spec.type === 'int' ? 'whole number' : 'number'}`;
        continue;
      }
      if (spec.type === 'int' && !Number.isInteger(parsed)) {
        errors[spec.name] = 'Must be a whole number';
        continue;
      }
      if (spec.minimum !== null && parsed < spec.minimum) {
        errors[spec.name] = `Must be at least ${spec.minimum}`;
        continue;
      }
      if (spec.maximum !== null && parsed > spec.maximum) {
        errors[spec.name] = `Must be at most ${spec.maximum}`;
      }
      continue;
    }

    if (spec.choices.length > 0 && !spec.choices.includes(raw)) {
      errors[spec.name] = `Must be one of: ${spec.choices.join(', ')}`;
    }
  }

  return errors;
}
