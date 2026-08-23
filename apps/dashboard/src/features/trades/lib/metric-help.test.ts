import { describe, expect, it } from 'vitest';
import { METRIC_HELP } from './metric-help';

const entries = Object.entries(METRIC_HELP);

describe('METRIC_HELP', () => {
  it('defines a non-empty what/why/interpretation for every metric', () => {
    for (const [key, help] of entries) {
      expect(help.what, `${key}.what`).toBeTruthy();
      expect(help.why, `${key}.why`).toBeTruthy();
      expect(help.interpretation, `${key}.interpretation`).toBeTruthy();
    }
  });

  it('writes every field as a complete sentence, so a screen reader announces prose', () => {
    for (const [key, help] of entries) {
      for (const [field, text] of Object.entries(help)) {
        expect(text.endsWith('.'), `${key}.${field} should end with a period`).toBe(true);
      }
    }
  });

  it('keeps each field concise enough for a tooltip', () => {
    for (const [key, help] of entries) {
      for (const [field, text] of Object.entries(help)) {
        expect(text.length, `${key}.${field} is too long for a tooltip`).toBeLessThan(320);
      }
    }
  });
});
