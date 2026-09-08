/**
 * Classifies a Marketaux `sentiment_score` (roughly -1 to 1, unbounded in
 * principle — see `services/api/app/connectors/marketaux.py`'s own
 * module docstring) into a real label, never just a color dot: the task
 * this page was built for explicitly requires an actual score or label
 * to be shown, not merely an implied-by-color signal.
 *
 * Thresholds are a deliberate, stated choice, not a discovered fact —
 * Marketaux's own docs describe the scale ("above 0 = positive, below 0
 * = negative") without naming a "neutral band," so a small dead zone
 * around zero avoids labeling a genuinely tiny, near-zero score as
 * confidently "Positive" or "Negative."
 */

export type SentimentLabel = 'positive' | 'neutral' | 'negative' | 'unknown';

const NEUTRAL_BAND = 0.1;

export function classifySentiment(score: number | null): SentimentLabel {
  if (score === null) return 'unknown';
  if (score > NEUTRAL_BAND) return 'positive';
  if (score < -NEUTRAL_BAND) return 'negative';
  return 'neutral';
}

export const SENTIMENT_LABEL_TEXT: Record<SentimentLabel, string> = {
  positive: 'Positive',
  neutral: 'Neutral',
  negative: 'Negative',
  unknown: 'No sentiment data',
};

/** e.g. "Positive (0.42)" — the label alongside its own real score,
 * never the label alone. */
export function formatSentiment(score: number | null): string {
  const label = SENTIMENT_LABEL_TEXT[classifySentiment(score)];
  if (score === null) return label;
  return `${label} (${score.toFixed(2)})`;
}
