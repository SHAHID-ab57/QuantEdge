/**
 * A rule-based classification of the *existing* rolling buy/sell imbalance
 * figure (`RollingAnalytics.buySellImbalance`, `lib/rolling-window.ts`) into
 * a human-readable label. This is deliberately just a fixed threshold table
 * over a number this codebase already computes — it predicts nothing and
 * recommends no action, so it is not AI, a model, or a trading signal; it
 * exists purely so the dashboard can show "Bullish" instead of asking a
 * researcher to mentally classify "+42%" themselves.
 */
export type SentimentLabel =
  'strongly-bullish' | 'bullish' | 'neutral' | 'bearish' | 'strongly-bearish';

export interface MarketSentiment {
  label: SentimentLabel;
  /** Display text, e.g. "Strongly Bullish". */
  text: string;
  /** The imbalance value this was derived from, passed through for display. */
  imbalance: number | null;
}

const STRONG_THRESHOLD = 0.5;
const MILD_THRESHOLD = 0.15;

const LABEL_TEXT: Record<SentimentLabel, string> = {
  'strongly-bullish': 'Strongly Bullish',
  bullish: 'Bullish',
  neutral: 'Neutral',
  bearish: 'Bearish',
  'strongly-bearish': 'Strongly Bearish',
};

/**
 * `imbalance` is `(buyVolume - sellVolume) / (buyVolume + sellVolume)` over
 * the trailing one-minute window, in `[-1, 1]`; `null` when that window has
 * no trades. Thresholds are symmetric around zero: `±0.5` and above is
 * "strongly" one-sided, `±0.15` and above is a mild lean, otherwise neutral.
 */
export function deriveSentiment(imbalance: number | null): MarketSentiment {
  if (imbalance === null) {
    return { label: 'neutral', text: LABEL_TEXT.neutral, imbalance: null };
  }
  let label: SentimentLabel;
  if (imbalance >= STRONG_THRESHOLD) {
    label = 'strongly-bullish';
  } else if (imbalance >= MILD_THRESHOLD) {
    label = 'bullish';
  } else if (imbalance <= -STRONG_THRESHOLD) {
    label = 'strongly-bearish';
  } else if (imbalance <= -MILD_THRESHOLD) {
    label = 'bearish';
  } else {
    label = 'neutral';
  }
  return { label, text: LABEL_TEXT[label], imbalance };
}
