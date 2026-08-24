/**
 * Plain-language explanations for every fixed field on the Technical
 * Indicators page (everything except a parameter, which varies per
 * indicator and is explained by `indicator-knowledge.ts` instead), kept in
 * one place so the wording stays consistent — matching the discipline
 * `trades/lib/metric-help.ts` established for the Trade Analytics
 * dashboard.
 */
export interface FieldHelp {
  what: string;
  why: string;
  interpretation: string;
}

export const FIELD_HELP = {
  market: {
    what: "The instrument the indicator is calculated on, sourced from the platform's tracked market catalogue.",
    why: "Every indicator value is a function of a specific market's price history — the same period-20 SMA is a different number on ETHUSD than on BTCUSD.",
    interpretation:
      'Only markets with stored candles for the chosen timeframe will return a result; the timeframe list narrows automatically once a market is picked.',
  },
  timeframe: {
    what: 'The candle resolution the indicator is calculated over — 1m, 15m, 1h, 1d, and so on.',
    why: 'The same indicator on the same market reads completely differently across timeframes: a 14-period RSI on 1-minute candles reacts to noise a 14-period RSI on daily candles would never notice.',
    interpretation:
      'Shorter timeframes suit short-term or intraday research; longer timeframes suit trend and regime analysis.',
  },
  indicator: {
    what: "The analytical calculation to run over the selected market's candles, resolved from the backend's indicator registry.",
    why: 'Different indicators answer different questions — trend indicators like SMA/EMA describe direction, momentum indicators like RSI describe speed and potential exhaustion.',
    interpretation:
      'The category groups indicators by what they measure; open Indicator Details below for a full explanation of the selected one.',
  },
  warmupCandles: {
    what: "The number of leading candles with no computed value, because the indicator's math needs a full window before it produces its first point.",
    why: 'A calculation range shorter than the warmup returns no usable series at all — the backend rejects it explicitly rather than silently returning an all-null result.',
    interpretation:
      'Equal to the period for a moving average, and one more than the period for RSI (its first candle produces no change to measure).',
  },
  candlesAnalyzed: {
    what: 'How many stored candles the calculation actually ran over, after the requested range and limit were applied.',
    why: "It's the sample size behind every other figure on this page — a two-candle SMA and a two-thousand-candle SMA carry very different statistical weight even with identical parameters.",
    interpretation:
      'Should sit well above Warmup Candles; if the two are close, most of the series will still be null.',
  },
  calculationTime: {
    what: "How long the indicator's own math took to run, separate from the time spent reading candles from the database.",
    why: 'Splitting the two makes it possible to tell whether a slow response was the calculation or the data fetch — useful once indicators get more expensive than a moving average.',
    interpretation:
      'For the reference indicators shipped so far this is sub-millisecond; a future, heavier indicator would show up here first.',
  },
  cacheStatus: {
    what: "Whether this exact calculation (same indicator, parameters, and candle range) was served from the engine's result cache or recomputed.",
    why: 'A hit skips redoing the math, though it never skips the database read — the cache key can only be built once the candles are already loaded.',
    interpretation:
      '"miss" on the first run of a configuration, "hit" on an identical repeat, "disabled" if the deployment has no cache configured.',
  },
  latestValue: {
    what: 'The most recent non-null value in this output series — the last point the indicator actually computed.',
    why: "It's the number a researcher checks first: where the indicator stands right now, at the most recent candle in the loaded range.",
    interpretation:
      'Compare it against the Previous Value and, where the indicator has one, an established threshold — RSI above 70, for example.',
  },
  resultsTable: {
    what: 'Every computed value, aligned one-for-one with the candle open time it belongs to, newest first.',
    why: "The alignment is the calculation's actual contract — a value in the wrong row would be silently wrong in a way that still looks plausible.",
    interpretation:
      'A dash (—) marks a warmup position, not a zero — the indicator simply had nothing to report yet at that candle.',
  },
} as const satisfies Record<string, FieldHelp>;

export type FieldKey = keyof typeof FIELD_HELP;
