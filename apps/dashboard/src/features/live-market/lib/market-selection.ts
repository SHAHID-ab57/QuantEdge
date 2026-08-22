import type { Market } from '@/types/api/market';

/**
 * Market selection for the Live Market Dashboard.
 *
 * The platform is an *Ethereum* research platform, and only the symbols the
 * backend actually tracks (`DELTA_MARKET_SYMBOLS`, `BTCUSD,ETHUSD` by
 * default) have candles or a live feed — the other ~223 markets in
 * `/markets` are catalogue entries with no data behind them. Selecting the
 * first market alphabetically therefore lands on something like
 * `1000BONKUSD` and renders an empty dashboard, which is what this module
 * exists to prevent.
 *
 * Everything here is a pure function of already-fetched data so the
 * ordering and fallback rules can be tested without a network or a render.
 */

/** The platform's primary research market — preferred whenever it is usable. */
export const PRIMARY_RESEARCH_SYMBOL = 'ETHUSD';

/**
 * How many candidates are probed for readiness. Each probe costs one
 * `/markets/{symbol}/timeframes` request, and the preferred symbols
 * (requested → remembered → ETHUSD → live-tracked) always sort to the
 * front, so a small cap is enough to find a good market without fanning
 * out hundreds of requests across a catalogue that is mostly empty.
 */
export const MAX_CANDIDATES = 6;

export interface MarketReadiness {
  symbol: string;
  /** Stored candles exist for at least one timeframe. */
  hasHistoricalCandles: boolean;
  /** The backend's state manager tracks this symbol, i.e. it is on the live feed. */
  hasLiveSupport: boolean;
  /** The backend currently holds a latest price for this symbol. */
  hasLatestPrice: boolean;
  /** Readiness could not be determined yet (the timeframes probe is still in flight). */
  isPending: boolean;
  /** Fully usable: historical candles *and* a live feed. */
  isReady: boolean;
  /** Human-readable reasons this market is not fully ready, for the empty state. */
  blockers: string[];
}

export interface AssessMarketInput {
  symbol: string;
  /** Timeframes with stored candles, or `undefined` while the probe is in flight. */
  timeframes: string[] | undefined;
  /** `state_latest_prices` from `/system/metrics`; `undefined` while loading. */
  livePrices: Record<string, string> | undefined;
}

/**
 * Scores one market against the dashboard's data requirements.
 *
 * Note that `hasLiveSupport` and `hasLatestPrice` come from the same
 * signal — the backend's in-memory state manager only holds a price for a
 * symbol it is streaming — but they are reported separately because they
 * fail for different reasons the user can act on: an untracked symbol needs
 * a config change, whereas a tracked symbol with no price yet just needs
 * the first tick to arrive.
 */
export function assessMarket({
  symbol,
  timeframes,
  livePrices,
}: AssessMarketInput): MarketReadiness {
  const isPending = timeframes === undefined || livePrices === undefined;
  const hasHistoricalCandles = (timeframes?.length ?? 0) > 0;
  const trackedSymbols = livePrices === undefined ? null : Object.keys(livePrices);
  const hasLiveSupport = trackedSymbols !== null && trackedSymbols.includes(symbol);
  const hasLatestPrice = Boolean(livePrices?.[symbol]);

  const blockers: string[] = [];
  if (!isPending && !hasHistoricalCandles) {
    blockers.push('No historical candles have been synchronized for this market.');
  }
  if (!isPending && !hasLiveSupport) {
    blockers.push(
      'This market is not on the backend live feed, so it receives no streaming updates.',
    );
  } else if (!isPending && !hasLatestPrice) {
    blockers.push('The backend is tracking this market but has not received a price yet.');
  }

  return {
    symbol,
    hasHistoricalCandles,
    hasLiveSupport,
    hasLatestPrice,
    isPending,
    isReady: !isPending && hasHistoricalCandles && hasLiveSupport,
    blockers,
  };
}

export interface CandidateInput {
  /** Symbol from the URL (`?symbol=`), which always wins if it is a real market. */
  requested: string | null;
  /** Symbol restored from local storage — the user's last selection. */
  remembered: string | null;
  markets: Market[] | undefined;
  livePrices: Record<string, string> | undefined;
}

/**
 * Builds the ordered list of symbols to probe, most-preferred first:
 * an explicit URL request, then the remembered selection, then the primary
 * research market, then whatever the backend is streaming, then any other
 * active market as a last resort. Unknown and inactive symbols are dropped,
 * and the result is capped at {@link MAX_CANDIDATES}.
 */
export function buildCandidateSymbols({
  requested,
  remembered,
  markets,
  livePrices,
}: CandidateInput): string[] {
  if (!markets || markets.length === 0) {
    return [];
  }
  const active = new Set(markets.filter((market) => market.is_active).map((m) => m.symbol));
  const liveSymbols = Object.keys(livePrices ?? {}).sort();

  const preferred = [requested, remembered, PRIMARY_RESEARCH_SYMBOL, ...liveSymbols];
  const fallback = markets.filter((market) => market.is_active).map((market) => market.symbol);

  const ordered: string[] = [];
  for (const symbol of [...preferred, ...fallback]) {
    if (symbol && active.has(symbol) && !ordered.includes(symbol)) {
      ordered.push(symbol);
      if (ordered.length === MAX_CANDIDATES) {
        break;
      }
    }
  }
  return ordered;
}

export interface MarketSelection {
  symbol: string | null;
  readiness: MarketReadiness | null;
  /** True while some candidate could still turn out to be ready. */
  isResolving: boolean;
}

/**
 * Picks the best market from the probed candidates.
 *
 * Preference order is fully ready (candles + live feed) → has candles →
 * first candidate. The last tier matters: an operator running with the live
 * feed disabled should still get a usable historical dashboard rather than
 * an empty page, so a market is never rejected outright — the gaps are
 * surfaced through {@link MarketReadiness.blockers} instead.
 */
export function selectResearchMarket(readiness: MarketReadiness[]): MarketSelection {
  if (readiness.length === 0) {
    return { symbol: null, readiness: null, isResolving: false };
  }

  const ready = readiness.find((entry) => entry.isReady);
  if (ready) {
    return { symbol: ready.symbol, readiness: ready, isResolving: false };
  }

  // Nothing is fully ready yet. While any probe is still in flight, a better
  // candidate may still appear, so report "resolving" rather than settling on
  // a degraded market and visibly switching away from it a moment later.
  const isResolving = readiness.some((entry) => entry.isPending);
  if (isResolving) {
    return { symbol: null, readiness: null, isResolving: true };
  }

  const withCandles = readiness.find((entry) => entry.hasHistoricalCandles);
  const chosen = withCandles ?? readiness[0]!;
  return { symbol: chosen.symbol, readiness: chosen, isResolving: false };
}
