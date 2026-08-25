import { describe, expect, it } from 'vitest';
import { ruleKnowledgeFor, suggestedFixFor } from './rule-knowledge';

const EXPECTED_RULES = [
  'required_columns',
  'data_types',
  'missing_values',
  'duplicate_rows',
  'duplicate_timestamps',
  'nan_values',
  'infinite_values',
  'timestamp_ordering',
  'time_gaps',
  'metadata_consistency',
  'feature_failures',
];

describe('ruleKnowledgeFor', () => {
  it('has curated content for every builtin rule', () => {
    for (const name of EXPECTED_RULES) {
      const knowledge = ruleKnowledgeFor(name);
      expect(knowledge.whyItMatters).not.toBe('Not yet documented for this rule.');
      expect(knowledge.exampleFailure).not.toBe('Not yet documented for this rule.');
    }
  });

  it('matches the exact duplicate_rows content requested for this feature', () => {
    expect(ruleKnowledgeFor('duplicate_rows').whyItMatters).toBe(
      'Duplicate observations bias statistical models.',
    );
  });

  it('degrades gracefully for an uncurated rule name', () => {
    const knowledge = ruleKnowledgeFor('some_future_rule');
    expect(knowledge.whyItMatters).toBe('Not yet documented for this rule.');
    expect(knowledge.exampleFailure).toBe('Not yet documented for this rule.');
  });
});

describe('suggestedFixFor', () => {
  it('has a suggested fix for a known issue code', () => {
    expect(suggestedFixFor('duplicate_timestamps')).not.toContain('Review the rule description');
  });

  it('falls back to a generic suggestion for an unknown code', () => {
    expect(suggestedFixFor('some_future_code')).toContain('Review the rule description');
  });
});
