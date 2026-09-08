import { describe, expect, it } from 'vitest';
import { classifySentiment, formatSentiment } from './sentiment-label';

describe('classifySentiment', () => {
  it('classifies a clearly positive score', () => {
    expect(classifySentiment(0.42)).toBe('positive');
  });

  it('classifies a clearly negative score', () => {
    expect(classifySentiment(-0.42)).toBe('negative');
  });

  it('classifies a near-zero score as neutral, not positive/negative', () => {
    expect(classifySentiment(0.05)).toBe('neutral');
    expect(classifySentiment(-0.05)).toBe('neutral');
    expect(classifySentiment(0)).toBe('neutral');
  });

  it('classifies a null score as unknown, never a fabricated neutral', () => {
    expect(classifySentiment(null)).toBe('unknown');
  });
});

describe('formatSentiment', () => {
  it('shows a real label alongside the real score, never the label alone', () => {
    expect(formatSentiment(-0.4215)).toBe('Negative (-0.42)');
    expect(formatSentiment(0.7783)).toBe('Positive (0.78)');
  });

  it('shows a plain "no sentiment data" label for null, with no score to show', () => {
    expect(formatSentiment(null)).toBe('No sentiment data');
  });
});
