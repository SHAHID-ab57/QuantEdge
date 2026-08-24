import type { Indicator } from '@/types/api/indicators';

export type SignalTone = 'bullish' | 'bearish' | 'neutral';

export interface ReferenceLine {
  value: number;
  label: string;
  tone: SignalTone;
}

export interface ChartConfig {
  /** 'oscillator' has a fixed, bounded domain (e.g. RSI's 0-100); 'line' scales to its own values. */
  kind: 'line' | 'oscillator';
  /** Fixed y-axis domain for an oscillator; omitted for a 'line' chart, which scales to its data. */
  domain?: [number, number];
  referenceLines?: ReferenceLine[];
}

export interface ParameterKnowledge {
  /** Longer than the backend's one-line `description` — explains why the parameter matters, not just what it is. */
  hint: string;
  /** Common values shown as clickable chips beneath the field. */
  recommended?: (string | number)[];
}

export interface IndicatorKnowledge {
  purpose: string;
  mathIntuition: string;
  /** Plain-text formula — this platform introduces no math-typesetting dependency for a handful of formulas. */
  formula: string;
  advantages: string[];
  limitations: string[];
  useCases: string[];
  interpretation: string;
  methodology?: string;
  parameters: Record<string, ParameterKnowledge>;
  chart: ChartConfig;
  /**
   * Indicator-specific reading of a value, when the indicator has an
   * established convention for one (e.g. RSI's 30/70 thresholds). Absent
   * for indicators where "bullish/bearish" isn't a meaningful label on the
   * value alone (e.g. a trend indicator, read only by comparing it to
   * price or to itself over time).
   */
  classifySignal?: (latest: number) => SignalTone;
}

const PRICE_SOURCE_HINT =
  'Which price of each candle feeds the calculation. "close" is the conventional default since it reflects where the market settled for that candle.';

/**
 * Curated research content for the indicators this engine ships today.
 * Deliberately separate from the backend's `IndicatorMetadata` — this is
 * frontend-only enrichment (methodology, formulas, interpretation
 * guidance), not part of the indicator contract, so it can grow richer
 * over time without ever requiring a backend change.
 */
const INDICATOR_KNOWLEDGE: Record<string, IndicatorKnowledge> = {
  sma: {
    purpose:
      'Smooths price by averaging the last N candles of a chosen price series, turning noisy tick-to-tick movement into a single trend line.',
    mathIntuition:
      'Every candle in the window counts equally, so the average only shifts when new data enters and old data leaves the window — it reacts to a change gradually rather than snapping to it.',
    formula: 'SMA(t) = (P(t) + P(t-1) + ... + P(t-N+1)) / N',
    advantages: [
      'Simple, transparent, and easy to reason about.',
      'Effective at filtering short-term noise to reveal the underlying trend.',
      'The same formula works identically on any price series.',
    ],
    limitations: [
      'Lags price — a large move takes N candles to fully show up in the average.',
      "Treats a candle from N periods ago exactly the same as yesterday's candle, which can feel wrong in a fast-moving market.",
      'On its own, gives no sense of momentum or speed, only direction.',
    ],
    useCases: [
      'Identifying the prevailing trend direction over a chosen horizon.',
      'A baseline for crossover systems (e.g. price crossing above/below a 200-period SMA).',
      'Smoothing volume or another series, not just price.',
    ],
    interpretation:
      'Price trading above a rising SMA is generally read as an uptrend, and below a falling SMA as a downtrend. The shorter the period, the more sensitive — and noisier — the line.',
    methodology:
      'Standard technical-analysis convention with no single original source; see any introductory technical analysis reference (e.g. Murphy, "Technical Analysis of the Financial Markets").',
    parameters: {
      period: {
        hint: 'The size of the averaging window, in candles. A short period reacts quickly but noisily; a long period is smoother but slower to reflect a real change.',
        recommended: [9, 20, 50, 100, 200],
      },
      source: {
        hint: PRICE_SOURCE_HINT,
        recommended: ['close', 'open', 'high', 'low'],
      },
    },
    chart: { kind: 'line' },
  },
  ema: {
    purpose:
      'Like the SMA, but weights recent candles more heavily, so it reacts faster to new price action while still smoothing out noise.',
    mathIntuition:
      'Each new value blends the previous EMA with the newest price, using a fixed multiplier derived from the period — a shorter period leans harder on the newest candle.',
    formula:
      'EMA(t) = (P(t) - EMA(t-1)) x k + EMA(t-1), where k = 2 / (period + 1); seeded from the SMA of the first full window.',
    advantages: [
      'Reacts faster to genuine trend changes than an SMA of the same period.',
      'Still smooths out a meaningful amount of short-term noise.',
      'Widely used, so its readings are comparable across research tools.',
    ],
    limitations: [
      'Faster reaction also means more false starts in a choppy, range-bound market.',
      'The recursive formula means an unusual value early in the series can influence every value after it.',
      "Like any moving average, it's a lagging measure — it describes what already happened, not what will.",
    ],
    useCases: [
      'A faster-reacting alternative to the SMA for the same crossover/trend-following use cases.',
      'The building block for MACD and other momentum indicators.',
      'Smoothing a noisy series (such as another indicator) for a second-order signal.',
    ],
    interpretation:
      'Reads the same way as an SMA — price above a rising EMA is bullish context — but expect it to hug price more closely and turn sooner at inflection points.',
    methodology:
      'Standard technical-analysis convention, popularized alongside MACD by Gerald Appel.',
    parameters: {
      period: {
        hint: 'The smoothing period; the multiplier 2/(period+1) is derived from it, so a smaller period weights recent candles much more heavily.',
        recommended: [9, 12, 20, 26, 50],
      },
      source: {
        hint: PRICE_SOURCE_HINT,
        recommended: ['close', 'open', 'high', 'low'],
      },
    },
    chart: { kind: 'line' },
  },
  rsi: {
    purpose:
      'A bounded 0-100 momentum oscillator comparing the size of recent gains to recent losses, to gauge whether a market is overbought, oversold, or neutral.',
    mathIntuition:
      "It tracks the average size of up-moves versus down-moves over the window using Wilder's smoothing (an EMA-like recursive average), then rescales that ratio onto a fixed 0-100 range so readings are comparable across any market or price level.",
    formula: 'RS = average gain / average loss (Wilder-smoothed); RSI = 100 - 100 / (1 + RS)',
    advantages: [
      'Fixed 0-100 scale makes readings directly comparable across different markets and price levels.',
      'Captures momentum/speed, which a moving average cannot express on its own.',
      'Well-studied conventional thresholds (30/70) give a common reference point.',
    ],
    limitations: [
      "Can stay in 'overbought' or 'oversold' territory for a long time during a strong trend, giving early or repeated false signals.",
      "A pure momentum reading — it says nothing about the trend's direction on its own.",
      'The 30/70 thresholds are a convention, not a law; different markets and timeframes warrant different levels.',
    ],
    useCases: [
      'Spotting potential exhaustion or reversal zones in range-bound markets.',
      'Divergence analysis: price making a new high/low while RSI does not.',
      'A filter alongside a trend indicator (e.g. only act on an oversold reading inside an established uptrend).',
    ],
    interpretation:
      'Conventionally read as overbought above 70 and oversold below 30, with 50 as the momentum midpoint. This platform surfaces the 30/50/70 levels for reference only and does not itself generate a trading signal.',
    methodology: 'J. Welles Wilder Jr., "New Concepts in Technical Trading Systems" (1978).',
    parameters: {
      period: {
        hint: "The look-back window for the smoothed gain/loss averages. Wilder's original — and still the most common choice — is 14; shorter periods are more volatile and cross 30/70 more often.",
        recommended: [7, 9, 14, 21, 25],
      },
      source: {
        hint: PRICE_SOURCE_HINT,
        recommended: ['close', 'open', 'high', 'low'],
      },
    },
    chart: {
      kind: 'oscillator',
      domain: [0, 100],
      referenceLines: [
        { value: 30, label: 'Oversold (30)', tone: 'bullish' },
        { value: 50, label: 'Midpoint (50)', tone: 'neutral' },
        { value: 70, label: 'Overbought (70)', tone: 'bearish' },
      ],
    },
    classifySignal: (latest) => {
      if (latest > 70) return 'bearish';
      if (latest < 30) return 'bullish';
      return 'neutral';
    },
  },
};

/**
 * A curated entry when one exists, or a generic-but-honest fallback built
 * from the backend's own catalogue metadata when it doesn't.
 *
 * This fallback is not a formality: the engine is explicitly designed to
 * grow toward hundreds of indicators (see `ARCHITECTURE.md` § "Technical
 * Indicator Engine"), and curated research content can only ever cover a
 * fraction of them. A future indicator must still render a complete,
 * non-broken Information Panel — just one that says plainly it hasn't
 * been curated yet, rather than fabricating a formula or advantages list
 * this module has no basis for.
 */
export function getIndicatorKnowledge(indicator: Indicator): IndicatorKnowledge {
  const curated = INDICATOR_KNOWLEDGE[indicator.name];
  if (curated) {
    return curated;
  }
  return {
    purpose: indicator.description,
    mathIntuition:
      "A detailed walkthrough hasn't been curated for this indicator yet — its exact calculation is owned by the backend's registered implementation.",
    formula: 'Not yet documented for this indicator.',
    advantages: [],
    limitations: [],
    useCases: [],
    interpretation:
      'Read the Latest Value below relative to its Previous Value and Trend Direction until indicator-specific interpretation guidance is added.',
    parameters: {},
    chart: { kind: 'line' },
  };
}
