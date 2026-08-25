import { describe, expect, it } from 'vitest';
import type { ValidationSummary } from '@/types/api/dataset-validation';
import { computeQualityScore, qualityBand } from './quality-score';

function summary(overrides: Partial<ValidationSummary> = {}): ValidationSummary {
  return { total_checks: 0, errors: 0, warnings: 0, info: 0, ...overrides };
}

describe('computeQualityScore', () => {
  it('is 100 for a perfectly clean report', () => {
    expect(computeQualityScore(summary())).toBe(100);
  });

  it('subtracts 15 per error', () => {
    expect(computeQualityScore(summary({ errors: 2 }))).toBe(70);
  });

  it('subtracts 5 per warning', () => {
    expect(computeQualityScore(summary({ warnings: 3 }))).toBe(85);
  });

  it('combines error and warning penalties', () => {
    expect(computeQualityScore(summary({ errors: 1, warnings: 2 }))).toBe(75);
  });

  it('never goes below zero', () => {
    expect(computeQualityScore(summary({ errors: 100 }))).toBe(0);
  });

  it('info findings never affect the score', () => {
    expect(computeQualityScore(summary({ info: 50 }))).toBe(100);
  });
});

describe('qualityBand', () => {
  it('classifies 90 and above as excellent', () => {
    expect(qualityBand(90)).toBe('excellent');
    expect(qualityBand(100)).toBe('excellent');
  });

  it('classifies 70-89 as good', () => {
    expect(qualityBand(70)).toBe('good');
    expect(qualityBand(89)).toBe('good');
  });

  it('classifies 40-69 as fair', () => {
    expect(qualityBand(40)).toBe('fair');
    expect(qualityBand(69)).toBe('fair');
  });

  it('classifies below 40 as poor', () => {
    expect(qualityBand(39)).toBe('poor');
    expect(qualityBand(0)).toBe('poor');
  });
});
