import type { ValidationRule } from '@/types/api/dataset-validation';

/**
 * Curated, frontend-only research content for the validation rules this
 * engine ships today — mirroring `features/indicators/lib/indicator-
 * knowledge.ts`'s exact pattern (a curated map plus a graceful, honest
 * fallback for anything uncurated), applied to validation rules instead of
 * indicators. Deliberately separate from the backend's
 * `ValidationRuleMetadata`: "why it matters" and "example failure" are
 * editorial content, not part of the rule contract, so this can grow
 * richer over time — including for a rule nobody has written yet — with
 * no backend change.
 */

export interface RuleKnowledge {
  whyItMatters: string;
  exampleFailure: string;
}

const RULE_KNOWLEDGE: Record<string, RuleKnowledge> = {
  required_columns: {
    whyItMatters:
      'A downstream model or pipeline that expects a specific column will fail — or silently misbehave — if that column never actually gets produced.',
    exampleFailure:
      'Requiring sma_20 as a required column without selecting sma with period=20 in the same request: the column is never produced, and validation reports a missing_required_column error.',
  },
  data_types: {
    whyItMatters:
      "A column whose values don't match its declared type (a string in a numeric column, say) breaks any downstream code that assumes a consistent type — including most model training code, which will raise or silently coerce the value.",
    exampleFailure:
      "A categorical column like candle_direction unexpectedly containing a numeric value alongside its usual 'up'/'down' strings.",
  },
  missing_values: {
    whyItMatters:
      'A training matrix with missing values makes most model libraries raise an error, or silently drop the row — either way, a researcher needs to know how many rows are affected before deciding how to handle it.',
    exampleFailure:
      'A feature that legitimately produces nulls beyond its warmup (e.g. a normalized wick ratio on a flat candle) leaves gaps in the delivered dataset.',
  },
  duplicate_rows: {
    whyItMatters: 'Duplicate observations bias statistical models.',
    exampleFailure:
      'Five candles that happen to share identical OHLCV values (a stalled market) produce five identical feature rows.',
  },
  duplicate_timestamps: {
    whyItMatters:
      "Two rows claiming the same timestamp make the dataset's time index ambiguous — any downstream code that indexes by timestamp (a join, a merge, a lookup) can silently pick the wrong row.",
    exampleFailure: "A data ingestion glitch stores the same candle's open_time twice.",
  },
  nan_values: {
    whyItMatters:
      'A NaN is a distinct defect from a missing value — it usually signals a computation bug (like a division by zero) rather than an intentional, reported absence, and most model libraries propagate NaN silently through every downstream calculation.',
    exampleFailure:
      "A ratio feature dividing by a candle's zero range produces NaN instead of a defined value or a reported null.",
  },
  infinite_values: {
    whyItMatters:
      'Infinite values break gradient-based model training outright (the loss becomes NaN or infinite) and are almost always a computation defect, not real market data.',
    exampleFailure:
      'A feature computing a rate of change divides by a near-zero denominator and overflows to infinity.',
  },
  timestamp_ordering: {
    whyItMatters:
      'Most time-series methods (rolling windows, walk-forward validation, autocorrelation) assume strictly increasing timestamps — an out-of-order row silently corrupts every calculation that depends on sequence.',
    exampleFailure:
      'A sorting bug in an upstream ingestion step delivers a candle out of chronological order.',
  },
  time_gaps: {
    whyItMatters:
      "A gap in the timestamp series means the dataset is missing observations at the timeframe's expected cadence — a rolling feature computed across a gap effectively spans a longer, unacknowledged period than its window implies.",
    exampleFailure:
      'An exchange outage leaves an hour-long hole in an otherwise-hourly candle series.',
  },
  metadata_consistency: {
    whyItMatters:
      "If the dataset's own row/column counts don't agree with its provenance record, something about how it was assembled is broken — treating it as valid would be building on top of an already-corrupt foundation.",
    exampleFailure:
      "A dataset's quality summary reports a different row count than the rows actually delivered.",
  },
  feature_failures: {
    whyItMatters:
      'A silently-missing feature changes what the model actually trains on without anyone asking for that — the same partial-success dataset can look complete at a glance while quietly missing a column a researcher assumed was there.',
    exampleFailure:
      'Requesting ema with a period longer than the available candle range: the feature fails to generate, and its columns are simply absent from the dataset.',
  },
};

const UNCURATED_KNOWLEDGE: RuleKnowledge = {
  whyItMatters: 'Not yet documented for this rule.',
  exampleFailure: 'Not yet documented for this rule.',
};

/**
 * A curated entry when one exists, or an honest "not yet documented"
 * fallback when it doesn't — the same graceful-degradation contract
 * `getIndicatorKnowledge` gives an uncurated indicator. The engine is
 * explicitly designed to grow past today's eleven builtin rules (see
 * `ARCHITECTURE.md` § "Dataset Validation & Quality Engine" — adding a
 * rule is one file), and a future rule must still render a complete panel,
 * just one that says plainly it hasn't been curated yet.
 */
export function ruleKnowledgeFor(name: string): RuleKnowledge {
  return RULE_KNOWLEDGE[name] ?? UNCURATED_KNOWLEDGE;
}

const SUGGESTED_FIX: Record<string, string> = {
  missing_required_column:
    'Select a feature that produces this column, or remove it from Required Columns.',
  missing_declared_column:
    'This indicates a defect in the feature that declared this column. Report it.',
  column_dtype_mismatch:
    "Inspect the generator producing this column — its output doesn't match its declared dtype.",
  missing_values:
    'Expected when the feature declares missing values as normal; otherwise inspect the generator for the affected column.',
  duplicate_rows:
    'Widen the requested feature set, or accept that the underlying market was genuinely flat over this period.',
  duplicate_timestamps:
    'Re-run market data validation on the stored candles for this market/timeframe — this should never happen.',
  nan_values: 'Inspect the generator for the affected column for a division or log by zero.',
  infinite_values:
    'Inspect the generator for the affected column for a division by a near-zero value.',
  timestamp_ordering: 'Re-sync or re-validate the stored candle data for this market/timeframe.',
  time_gaps:
    'Widen the date range, choose a different period, or accept the gap if the market was genuinely inactive.',
  row_timestamp_mismatch: 'This indicates a defect in dataset assembly. Report it.',
  row_column_mismatch: 'This indicates a defect in dataset assembly. Report it.',
  quality_row_count_mismatch: 'This indicates a defect in dataset assembly. Report it.',
  feature_generation_failed:
    "Adjust the failing feature's parameters (e.g. reduce a period that exceeds the available range), or remove it from the request.",
};

/**
 * A suggested next step for one issue, keyed by its `code` rather than its
 * `rule` — a single rule can emit more than one distinct code (e.g.
 * `required_columns` emits both `missing_required_column` and
 * `missing_declared_column`), each warranting different guidance.
 */
export function suggestedFixFor(code: string): string {
  return (
    SUGGESTED_FIX[code] ?? 'Review the rule description and the affected column/row for context.'
  );
}

/** Every rule this module has curated content for — used only by tests to keep the two lists honest. */
export function knownRuleNames(rules: readonly ValidationRule[]): string[] {
  return rules.map((rule) => rule.name).filter((name) => name in RULE_KNOWLEDGE);
}
