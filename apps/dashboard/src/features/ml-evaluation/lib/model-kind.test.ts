import { describe, expect, it } from 'vitest';
import { toModelKind } from './model-kind';

describe('toModelKind', () => {
  it('passes through a recognized model kind', () => {
    expect(toModelKind('classification')).toBe('classification');
    expect(toModelKind('regression')).toBe('regression');
    expect(toModelKind('placeholder')).toBe('placeholder');
  });

  it('returns undefined for an unrecognized value', () => {
    expect(toModelKind('unknown')).toBeUndefined();
    expect(toModelKind('')).toBeUndefined();
  });
});
