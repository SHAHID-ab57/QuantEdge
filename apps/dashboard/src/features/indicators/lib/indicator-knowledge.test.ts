import { describe, expect, it } from 'vitest';
import type { Indicator } from '@/types/api/indicators';
import { getIndicatorKnowledge } from './indicator-knowledge';

function catalogueEntry(overrides: Partial<Indicator> = {}): Indicator {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'The unweighted mean of the last N values.',
    category: 'trend',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period parameter.',
    parameters: [],
    outputs: [],
    ...overrides,
  };
}

describe('getIndicatorKnowledge — curated entries', () => {
  it('returns a complete curated entry for sma', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'sma' }));
    expect(knowledge.purpose).toContain('Smooths price');
    expect(knowledge.formula).toContain('SMA(t)');
    expect(knowledge.advantages.length).toBeGreaterThan(0);
    expect(knowledge.limitations.length).toBeGreaterThan(0);
    expect(knowledge.parameters.period?.recommended).toEqual([9, 20, 50, 100, 200]);
    expect(knowledge.chart.kind).toBe('line');
  });

  it('gives rsi a bounded oscillator chart with 30/50/70 reference lines', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'rsi' }));
    expect(knowledge.chart.kind).toBe('oscillator');
    expect(knowledge.chart.domain).toEqual([0, 100]);
    expect(knowledge.chart.referenceLines?.map((line) => line.value)).toEqual([30, 50, 70]);
  });

  it('classifies rsi using its own thresholds, not a generic fallback', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'rsi' }));
    expect(knowledge.classifyState?.(80)).toEqual({ label: 'Overbought', tone: 'notable' });
    expect(knowledge.classifyState?.(20)).toEqual({ label: 'Oversold', tone: 'notable' });
    expect(knowledge.classifyState?.(50)).toEqual({ label: 'Neutral', tone: 'neutral' });
  });

  it('gives ema a recursive-formula description distinct from sma', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'ema' }));
    expect(knowledge.formula).toContain('EMA(t-1)');
  });

  it('gives wma a linear-weighting formula distinct from sma and ema', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'wma' }));
    expect(knowledge.formula).toContain('1+2+...+N');
    expect(knowledge.chart.kind).toBe('line');
    expect(knowledge.parameters.period?.recommended).toEqual([9, 20, 50, 100, 200]);
  });

  it('every curated entry declares a source parameter with price choices', () => {
    for (const name of ['sma', 'ema', 'wma', 'rsi']) {
      const knowledge = getIndicatorKnowledge(catalogueEntry({ name }));
      expect(knowledge.parameters.source?.recommended).toEqual(['close', 'open', 'high', 'low']);
    }
  });
});

describe('getIndicatorKnowledge — generic fallback', () => {
  it('never returns undefined for an indicator the knowledge base has never seen', () => {
    // The engine is explicitly designed to grow toward hundreds of
    // indicators — a curated miss must still render something honest,
    // not break.
    const knowledge = getIndicatorKnowledge(
      catalogueEntry({ name: 'macd', description: 'Moving Average Convergence Divergence.' }),
    );
    expect(knowledge).toBeDefined();
    expect(knowledge.purpose).toBe('Moving Average Convergence Divergence.');
  });

  it('does not fabricate a formula, advantages, or limitations for an uncurated indicator', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'macd' }));
    expect(knowledge.formula).toBe('Not yet documented for this indicator.');
    expect(knowledge.advantages).toEqual([]);
    expect(knowledge.limitations).toEqual([]);
    expect(knowledge.useCases).toEqual([]);
    expect(knowledge.methodology).toBeUndefined();
  });

  it('has no per-parameter knowledge, but does not throw when parameters are looked up', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'macd' }));
    expect(knowledge.parameters.period).toBeUndefined();
  });

  it('falls back to a line chart with no reference lines', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'macd' }));
    expect(knowledge.chart).toEqual({ kind: 'line' });
  });

  it('has no state classifier — an uncurated indicator gets no fabricated reading', () => {
    const knowledge = getIndicatorKnowledge(catalogueEntry({ name: 'macd' }));
    expect(knowledge.classifyState).toBeUndefined();
  });
});
