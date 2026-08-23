import { describe, expect, it } from 'vitest';
import { deriveSentiment } from './sentiment';

describe('deriveSentiment', () => {
  it('reports neutral with a null imbalance when there is no data', () => {
    expect(deriveSentiment(null)).toEqual({ label: 'neutral', text: 'Neutral', imbalance: null });
  });

  it('classifies strongly bullish at or above +0.5', () => {
    expect(deriveSentiment(0.5).label).toBe('strongly-bullish');
    expect(deriveSentiment(1).label).toBe('strongly-bullish');
  });

  it('classifies bullish between +0.15 and +0.5', () => {
    expect(deriveSentiment(0.15).label).toBe('bullish');
    expect(deriveSentiment(0.49).label).toBe('bullish');
  });

  it('classifies neutral between -0.15 and +0.15', () => {
    expect(deriveSentiment(0).label).toBe('neutral');
    expect(deriveSentiment(0.1).label).toBe('neutral');
    expect(deriveSentiment(-0.1).label).toBe('neutral');
  });

  it('classifies bearish between -0.5 and -0.15', () => {
    expect(deriveSentiment(-0.15).label).toBe('bearish');
    expect(deriveSentiment(-0.49).label).toBe('bearish');
  });

  it('classifies strongly bearish at or below -0.5', () => {
    expect(deriveSentiment(-0.5).label).toBe('strongly-bearish');
    expect(deriveSentiment(-1).label).toBe('strongly-bearish');
  });

  it('passes the imbalance value through for display', () => {
    expect(deriveSentiment(0.33).imbalance).toBe(0.33);
  });

  it('gives every label a distinct display text', () => {
    const texts = new Set([-1, -0.3, 0, 0.3, 1].map((value) => deriveSentiment(value).text));
    expect(texts.size).toBe(5);
  });
});
