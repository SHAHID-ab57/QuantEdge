/**
 * Plain-language explanations for every metric on the Trade Analytics
 * dashboard, kept in one place rather than scattered across component
 * files, so the wording stays consistent and a metric that appears in two
 * panels can never drift into two different explanations.
 *
 * Each entry answers the same four questions, in the same order, deliberately
 * pitched at a reader who knows markets but not this dashboard:
 *
 * - `what` — what the number is, in one sentence.
 * - `why` — why a researcher would look at it.
 * - `how` — the calculation, when it isn't self-evident from the name.
 * - `interpretation` — how to read a typical value.
 */
export interface MetricHelp {
  what: string;
  why: string;
  how?: string;
  interpretation: string;
}

export const METRIC_HELP = {
  currentPrice: {
    what: 'The price of the most recent trade to print on this feed.',
    why: 'It is the market’s live reference point — every other figure here is measured against it.',
    interpretation:
      'Coloured green when the last trade was a buy (the taker lifted the offer) and red when it was a sell. The colour describes that single trade, not a trend.',
  },
  sessionHigh: {
    what: 'The highest price traded since this page connected.',
    why: 'Together with the session low it frames the range the market has actually traded in, which is the context a single price lacks.',
    interpretation:
      'A current price pinned near the session high means buyers have been in control of the range so far.',
  },
  sessionLow: {
    what: 'The lowest price traded since this page connected.',
    why: 'Together with the session high it frames the range the market has actually traded in.',
    interpretation:
      'A current price pinned near the session low means sellers have been in control of the range so far.',
  },
  vwapDistance: {
    what: 'How far the current price sits above or below the session VWAP.',
    why: 'VWAP is the benchmark most execution desks are measured against, so “above or below VWAP” is the usual shorthand for whether buyers or sellers have had the better of the session.',
    how: '(current price − session VWAP) ÷ session VWAP, shown as a percentage.',
    interpretation:
      'Positive (green) means the market is trading above its average execution price this session; negative (red) means below. Values near 0% mean price and VWAP have converged.',
  },
  tradesPerSecond: {
    what: 'How many trades are printing per second, measured over the last ten seconds.',
    why: 'It is the quickest read on whether the market is currently active or quiet — useful before trusting any short-window statistic on this page.',
    how: 'Trades in the trailing ten seconds ÷ 10. A short window is used deliberately so a burst or a lull shows up immediately rather than being averaged away.',
    interpretation:
      'Sustained high values mean an active market where the one-minute figures are well-populated; near zero means the rolling windows are running on very little data.',
  },
  buyVolume: {
    what: 'Total quantity bought by aggressors since this page connected.',
    why: 'Splitting volume by aggressor side is the basis of every order-flow read on this page.',
    interpretation:
      'Compare it against sell volume — the ratio matters far more than the raw number.',
  },
  sellVolume: {
    what: 'Total quantity sold by aggressors since this page connected.',
    why: 'Splitting volume by aggressor side is the basis of every order-flow read on this page.',
    interpretation:
      'Compare it against buy volume — the ratio matters far more than the raw number.',
  },
  totalVolume: {
    what: 'Total quantity traded since this page connected, both sides combined.',
    why: 'It is the denominator behind the session VWAP and the average trade size, and the simplest measure of how much has actually changed hands.',
    interpretation:
      'Meaningful mostly as a trend and in comparison with other sessions, not as an absolute figure.',
  },
  buySellRatio: {
    what: 'Buy volume divided by sell volume for the whole session.',
    why: 'A single number for which side has been more aggressive overall.',
    how: 'Buy volume ÷ sell volume. Shown as Unavailable rather than infinity when no sells have printed yet.',
    interpretation:
      'Above 1.00 means buyers have lifted more than sellers have hit; below 1.00 the reverse. Values close to 1.00 mean balanced two-way flow.',
  },
  avgTradeSize: {
    what: 'Average quantity per trade.',
    why: 'It separates “many small trades” from “a few large ones”, which is the difference between retail-sized flow and institutional participation.',
    how: 'Total volume ÷ number of trades.',
    interpretation:
      'A rising average alongside steady trade counts means individual prints are getting larger. Check the size distribution before trusting this alone — a few outsized trades can pull it far from typical.',
  },
  tradeCount: {
    what: 'Number of trades observed since this page connected.',
    why: 'It tells you how much data every session-wide statistic here is actually built on.',
    interpretation:
      'Low counts mean the session figures are still noisy; they stabilise as the count grows.',
  },
  sessionVwap: {
    what: 'Volume-weighted average price of every trade since this page connected.',
    why: 'It is the benchmark execution price for the session — the level at which the average unit of volume actually traded.',
    how: 'Sum of (price × quantity) ÷ total quantity. “Session” here means since this browser tab subscribed, not the exchange’s own trading-session boundary, which this platform has no historical trade log to reconstruct.',
    interpretation:
      'Price above VWAP means buyers have paid up relative to the session average; below means sellers have accepted less.',
  },
  rollingVwap: {
    what: 'Volume-weighted average price over a fixed trailing window (1, 5, or 15 minutes).',
    why: 'Shorter windows react quickly to fresh flow, while the session VWAP is slow to move once a session has run for a while.',
    how: 'Same calculation as session VWAP, restricted to trades inside the window.',
    interpretation:
      'A 1-minute VWAP pulling away from the 15-minute one signals a short-term move away from the recent average.',
  },
  tradesPerMinute: {
    what: 'Number of trades in the trailing sixty seconds.',
    why: 'A steadier read on activity than trades per second, and the sample size behind every other one-minute figure here.',
    interpretation:
      'Rising counts mean the market is speeding up. When it falls to near zero, treat the other rolling figures as thin.',
  },
  volumePerMinute: {
    what: 'Total quantity traded in the trailing sixty seconds.',
    why: 'Volume, unlike trade count, weighs a single large print appropriately — the two rising together confirm genuine participation.',
    interpretation:
      'Volume rising while trade count stays flat means the individual prints are getting bigger.',
  },
  rollingAvgTradeSize: {
    what: 'Average quantity per trade in the trailing sixty seconds.',
    why: 'Comparing it against the session average shows whether the size of participation is changing right now.',
    how: 'Volume in the last minute ÷ trades in the last minute.',
    interpretation:
      'Well above the session average means larger-than-usual prints are hitting the tape at the moment.',
  },
  buySellImbalance: {
    what: 'Which side dominated the trailing sixty seconds, on a −100% to +100% scale.',
    why: 'It normalises the buy/sell split so it can be compared across quiet and busy minutes alike.',
    how: '(buy volume − sell volume) ÷ (buy volume + sell volume) over the last minute. Trades whose side the exchange did not report are excluded.',
    interpretation:
      '+100% means every unit traded was aggressive buying, −100% every unit aggressive selling, and 0% a perfectly balanced minute.',
  },
  marketSentiment: {
    what: 'A plain-language label for the current buy/sell imbalance.',
    why: 'It saves you converting a percentage into a judgement each time you glance at the page.',
    how: 'A fixed threshold table over the one-minute imbalance: ±50% or more is “Strongly” one-sided, ±15% or more is a mild lean, anything between is Neutral.',
    interpretation:
      'This describes the minute that just happened. It is not a forecast, a model output, or a trading signal.',
  },
  buySellPressure: {
    what: 'Buy volume’s share of traded volume versus sell volume’s, drawn as a proportional bar.',
    why: 'Reading a split as a bar is faster than reading it as a ratio, and it makes small changes visible at a glance.',
    interpretation:
      'A bar dominated by green means buyers took most of the volume over that window; red means sellers did. An even split is balanced two-way flow.',
  },
  buySellVolumeTrend: {
    what: 'Buy volume and sell volume over the last few minutes, drawn as two overlaid trend lines.',
    why: 'A single imbalance percentage tells you where the flow is now; these lines tell you whether it got there gradually or flipped suddenly.',
    how: 'Each line samples that side’s one-minute volume roughly every two seconds. The two lines are scaled independently, so compare their shapes rather than their heights.',
    interpretation:
      'Both lines rising together is a market getting busier on both sides. One rising while the other flattens is genuine one-way pressure building.',
  },
  largestTrade: {
    what: 'The single biggest trade by notional value, with its time, side, price, and quantity.',
    why: 'Outsized prints are where market impact comes from, and they are often what pulled the average trade size away from typical.',
    how: 'Ranked by price × quantity, not quantity alone — a large quantity of a cheap asset and a small quantity of an expensive one are not comparable by quantity.',
    interpretation:
      'Check its timestamp: a large print from a while ago says less about the current market than one that just hit.',
  },
  sizeDistribution: {
    what: 'How the last minute’s trades break down by size, in multiples of that minute’s own average.',
    why: 'The average trade size alone hides the shape of the flow; this shows whether it is many similar prints or a few outliers dragging the average.',
    how: 'Each trade is bucketed by (its size ÷ the window’s average size). Bucketing relative to the average rather than to absolute quantities makes the shape comparable across any market.',
    interpretation:
      'Weight concentrated in the small buckets is retail-sized flow. A fat ≥5× bucket means a handful of large prints are carrying the volume — treat the average trade size with caution when you see it.',
  },
  tradeValue: {
    what: 'The notional value of a trade: its price multiplied by its quantity.',
    why: 'It is the comparable measure of how big a trade really was, independent of the asset’s price level.',
    interpretation:
      'Rows flagged “Large” are trades worth at least five times the session’s average trade value.',
  },
} as const satisfies Record<string, MetricHelp>;

export type MetricKey = keyof typeof METRIC_HELP;
