# Liquidation Heatmap — Data Source Investigation

**Type:** Research spike (M4-E2-T2, the last open item in Milestone 4's
Epic 4.2). No application code, no connector, no Feature Engineering Engine
changes, no order-flow-capture changes — this document is the deliverable.

**Trigger.** `M4-E2-T2` was carried in `TASKBOOK.md` since M4-E2-T1 as
**Deferred / Low priority**, on the strength of one fact: a repo-wide
search for "liquidation" found zero existing code or documentation for a
market-wide heatmap feature, only a private, per-position
`liquidation_price` field in Delta's own account-margin WebSocket model
(`app/integrations/delta/websocket/models.py`'s `PositionUpdate`/
`PositionsEvent`). That earlier finding was about _this repository_. This
investigation is about the _outside world_: what "liquidation heatmap"
actually means across the industry, what Delta Exchange India's real,
current API does and doesn't expose, and what it would genuinely cost to
build either version from a third party.

## TL;DR verdict

**"Liquidation heatmap" is not one thing — it is two genuinely different
data products that happen to share a name, and neither is available from
Delta Exchange India at any price.** (a) A chart of _actual_ liquidation
events (Binance's public `forceOrder` stream, Coinglass's "Liquidation
Order"/"Liquidation History" endpoints) and (b) an _estimated_ heatmap of
where leverage clusters would probably get force-closed, modeled from
open interest and an assumed leverage distribution (Coinglass's and
Hyblock's flagship "Liquidation Heatmap" products — the meaning most
people actually intend by the term, per every industry source checked
below). Delta's current REST and WebSocket API documentation, checked
directly today, contains **no liquidation feed of either kind** — the
only liquidation-related trace anywhere in it is a private,
per-account order-type enum value. Every real option is a third party,
and every meaningful one costs money: Coinglass's cheapest tier that
includes _any_ liquidation data is $299/mo (real events only); its actual
heatmap model requires $699/mo. The one free option — Binance's public
`forceOrder` stream — only gets you definition (a), only for Binance's
own market (an explicit proxy, not this platform's own exchange), and
under-samples during volatility bursts by its own documented design.
**Recommendation: do not build this now** — see § Recommendation for the
full reasoning and the fallback path if the decision goes the other way.

---

## 1. What "liquidation heatmap" actually means

The task named two candidate definitions and asked that both be presented,
not pre-selected. Checked against how the term is actually used across
the tools that popularized it (Coinglass, Hyblock, Coinalyze, DEXTools,
Zipmex, CoinLobster — see Sources), the industry itself draws the same
two-way split, described consistently across independent sources:

### (a) Actual historical liquidation events

A chart or feed of **real, executed** forced-close orders, aggregated by
price and time after the fact. This is ground truth — an exchange's own
matching engine actually closed a position at that price, at that
moment — not a model. Coinalyze's real-time liquidation ticker and
Coinglass's "Liquidation Order"/"Liquidation History" endpoints are this
kind. Binance's public `forceOrder` WebSocket stream (§ 3.3) is the
canonical free source of this kind of data, for Binance's own market.

**What it needs:** an exchange that actually _publishes_ its own
liquidation events publicly (most don't — see § 2), or a third party that
already aggregates them from the exchanges that do. Engineering shape:
a streaming ingestion path (a persistent WebSocket subscription, pushed
continuously) plus a store to aggregate by price bucket and time bucket
for the chart — closer in shape to the Delta WebSocket client this
platform already runs than to the periodic-REST-poll `Connector` protocol
the six existing connectors use (see § 4).

### (b) Estimated liquidation-cluster heatmap

A **modeled, probabilistic** visualization of where large clusters of
leveraged positions would _likely_ be force-closed at a given price,
inferred — never observed directly — from open interest, recent trading
volume/funding flow, and an assumed distribution of leverage in use
(e.g., "10x, 25x, 50x, 100x" tiers). This is what Coinglass's own
flagship "Liquidation Heatmap" product is, and it is the meaning most
casual references to "liquidation heatmap" actually intend — multiple
independent sources describe it the same way: _"Public exchanges do not
publish entry price or leverage per position. Heatmap providers
reconstruct the picture from open interest, funding flows, recent trade
volume, and a leverage-usage model"_ (see Sources). Coinglass itself
documents two named leverage models for this exact reason (Model 1:
high-leverage only — 10x/25x/50x/100x; Model 2: all leverage tiers
including 2x/3x/5x) — a tell that this is an assumption-driven estimate,
not a measurement, and that the assumption is itself a product design
choice with more than one reasonable answer.

**What it needs:** open interest (already ingested by this platform as
part of M4-E2-T1's own funding/OI completion work — `TickerEvent
.open_interest`, `MarketStateManager`), a chosen leverage-distribution
model (a genuine, disclosed assumption — there is no way to observe real
leverage-per-position from public market data), and either building that
model in-house or buying it pre-computed from a vendor that already has
one. Engineering shape: closer to the existing connector pattern (a
periodic model recompute, not a continuous event stream) — but the model
itself, and its accuracy, is the hard, unsolved part; the data-fetching
part is comparatively easy.

**Neither definition is "the" liquidation heatmap** — both are real,
named, sold products in the market today, under the same name, and this
document does not pick one on the industry's behalf. § 4 recommends
_neither_ be built right now, for the same reasons under both.

---

## 2. Delta Exchange India's own API — checked directly, today

The task called this out specifically as a distinct check from the
funding-rate/open-interest investigation (M4-E2-T1) — liquidations are a
different event type, and an earlier finding about this platform's own
funding/OI wiring gap must not be assumed to generalize to liquidations.
It doesn't need to: the two questions turned out to have opposite
answers. Checked directly against Delta's own current documentation
(`docs.delta.exchange`, its REST reference, and its community
API-updates/announcements board — not this platform's own client code,
and not assumed from the M4-E2-T1 investigation):

- **No dedicated liquidation REST endpoint exists.** The REST API's own
  table of contents (Assets, Indices, Products, Orders, Positions,
  TradeHistory, Orderbook, Trades, Wallet, Stats, MMP, Account, Heartbeat
  Management, Settlement Prices, Historical OHLC Candles, Schemas,
  Deadman Switch) has no liquidation section, and no endpoint under any
  other section returns liquidation events.
- **No dedicated liquidation WebSocket channel exists.** The documented
  public channels are `ticker`, `l2_orderbook`/`ob_l1`/`ob_updates`,
  `trades`/`all_trades`, `funding_rate`, `mark_price`, `system_status`,
  and `product_updates`; the documented private channels are `orders`,
  `positions`, `margins`. None of them is a liquidation feed.
- **The public `trades`/`all_trades` channel carries no liquidation
  flag.** A trade record's own fields (`symbol`, `price`, `size`,
  `buyer_role`) say nothing about whether that fill was a normal order or
  a forced liquidation — confirmed against both the official schema and
  a third-party client's own field-by-field guide, independently, since
  the official docs site did not render its full schema table to this
  investigation's fetch. This platform's own `TradesEvent`/normalizer
  already reflects that exact field set (`app/integrations/delta
/websocket/models.py`, `app/marketdata/normalizer.py`'s
  `_TRADE_SIDE_BY_BUYER_ROLE`) — there is nothing to newly extract here.
- **The only liquidation-related trace anywhere in Delta's documented
  API** is `stop_order_type: "liquidation_order"` — one enumerated value
  in the Orders schema, documented as _"Order automatically generated by
  the system to close a position during liquidation."_ This is a
  **private, per-account** fact (visible only via the authenticated
  `orders`/`positions` channels, only for the caller's own account),
  exactly matching the `PositionUpdate.liquidation_price` field this
  platform's own Delta WebSocket models already carry (found in the
  M4-E2-T2 deferral note that opened this task) — Delta tells you _your
  own_ liquidation price if you hold a position; it does not publish
  _anyone's_ liquidation events, or open interest's leverage composition,
  to the public market.
- **No planned or recent addition.** Delta's own API Updates &
  Announcements board (`community.delta.exchange`) was scanned for any
  mention of a liquidation feed, channel, or endpoint being added,
  historically or recently. None of its announcements — covering
  category changes, history-endpoint parameter clarifications, scheduled
  maintenance, and general changelog entries — mentions liquidation at
  all.

**Conclusion: Delta Exchange India provides zero public, market-wide
liquidation data of either kind (real events or a modeled heatmap), and
nothing in its public roadmap suggests that changing.** This re-confirms
and extends the earlier repo-wide-grep finding with a live check of the
actual current external documentation, as the task required — the answer
did not change, but it is no longer inferred from the absence of code in
this repository alone.

---

## 3. Third-party options

Since Delta provides nothing, any liquidation heatmap of either kind
requires an external source. Two were investigated, per the task.

### 3.1 Coinglass — the market leader for both definitions

Coinglass is the source most industry commentary means by "liquidation
heatmap" (§ 1), and it offers API products for both definitions. Checked
directly against `docs.coinglass.com` and `coinglass.com/pricing`.

**Pricing tiers** (API access, not the web-dashboard subscription):

| Tier         | Price   | Rate limit    | Notes                                                                                                      |
| ------------ | ------- | ------------- | ---------------------------------------------------------------------------------------------------------- |
| Free         | $0      | —             | 10,000 calls/month; **no liquidation endpoints** — real-time market data only (see caveat below)           |
| Hobbyist     | $29/mo  | 30 req/min    | 80+ endpoints; **personal use only** (no commercial use)                                                   |
| Startup      | $79/mo  | 80 req/min    | 130+ endpoints; personal use only                                                                          |
| Standard     | $299/mo | 300 req/min   | 150+ endpoints; **first tier with commercial-use rights**; **first tier with real liquidation-event data** |
| Professional | $699/mo | 1,200 req/min | 160+ endpoints; **first tier with the Liquidation Heatmap model**                                          |
| Enterprise   | Custom  | Custom        | Quote-only                                                                                                 |

**Definition (a) — real events**, `GET /futures/liquidation/order`
(liquidation prints from the last 7 days: exchange, symbol, price,
USD value, side, timestamp; 1-second cache): gated to **Standard tier and
above ($299/mo)** — its own docs page's tier-availability table marks
Hobbyist and Startup both `❌`. A companion "Liquidation History"
endpoint (aggregated long/short totals per pair) and an "Aggregated
Liquidation History" endpoint (aggregated across exchanges, per coin)
exist under the same family; neither's exact tier gating was checked
individually — recommend re-verifying if this path is pursued, but there
is no indication either drops below Standard.

**Definition (b) — the modeled heatmap**, `GET
/futures/liquidation/heatmap/model1` (`exchange`, `symbol`, `range` in:
`12h, 24h, 3d, 7d, 30d, 90d, 180d, 1y`; returns `y_axis` price levels,
`liquidation_leverage_data` as `[x, y, leverage-value]` triples, plus
`price_candlesticks` for the OHLCV overlay): gated to **Professional and
Enterprise only ($699/mo+)** — explicitly stated on its own docs page as
unavailable to Hobbyist, Startup, and Standard. A "Model3" variant and an
aggregated (multi-exchange) heatmap variant exist under the same family
at the same or a higher tier.

**A caveat worth stating plainly, since search summaries disagreed with
the primary docs**: a preliminary web search characterized Coinglass's
free plan as including "real-time liquidation data." Checked directly
against the endpoints' own documentation pages, this is not accurate for
API access — every liquidation endpoint's own tier-availability table
excludes the free tier. The likely source of that looser claim is
Coinglass's public **website** displaying some liquidation charts for
free to human visitors (a marketing/dashboard surface), which is a
different product from **programmatic API access** to the same data —
this platform would need the latter. Stated here explicitly so this
distinction isn't lost if this document is read later without the
underlying pages re-checked.

**Commercial-use note**: this platform is a product serving other users,
not personal research — Coinglass's own terms restrict commercial use to
Standard tier and above regardless of which specific endpoint is used,
so Hobbyist/Startup are not a viable cheaper substitute even if a lower
tier happened to include a needed endpoint.

Hyblock Capital was also found to offer a comparable modeled "Liquidation
Heatmap" API product (`docs.hyblockcapital.com/liquidation-heatmap`),
priced and gated similarly (a paid-tier, non-free product) — not
investigated to the same depth as Coinglass since the task named
Coinglass specifically, but noted here as evidence this is an
industry-standard paid product category, not a Coinglass-specific
pricing choice this platform could shop around.

### 3.2 A major exchange's public liquidation feed as a market-wide proxy

Binance publishes a genuinely free, public, real-event liquidation
stream — the only free option found for either definition, anywhere.

**`forceOrder` WebSocket stream** (`wss://fstream.binance.com`,
USDⓈ-M futures; a parallel Coin-M variant exists):

- **Public, no authentication or API key required.**
- Two stream names: `<symbol>@forceOrder` (one symbol, e.g.
  `ethusdt@forceOrder`) or `!forceOrder@arr` (every symbol on the
  venue).
- Event fields: event type, event time, symbol, side (`BUY`/`SELL`),
  order type, time-in-force, quantity fields, price, average price,
  order status, and trade time — a real, executed liquidation order,
  not a model.
- **A real, documented sampling limitation**: _"only the largest one
  liquidation order within 1000ms will be pushed"_ per symbol — if
  several positions liquidate on the same symbol within the same second
  (exactly the scenario a real heatmap chart most wants to capture — a
  cascade), this stream reports only the single largest one and silently
  drops the rest. It is a real-events feed, but an intentionally
  down-sampled one, not a complete tape.

**Stated plainly, per the task**: using this would mean building a
**Binance market-wide liquidation proxy**, not this platform's own
exchange's actual liquidations. Delta Exchange India publishes none
(§ 2) — there is no way to show "Delta's own liquidations" because Delta
does not make them observable to anyone outside the position holder.
Binance's ETH/BTC perpetual liquidations are a reasonable proxy for
_aggregate crypto-market leverage stress_ (Binance is the largest
venue by volume), but they are not Delta's own market microstructure,
and presenting them as if they were this platform's own exchange data
would misrepresent the source. Any feature built on this must label
itself as a cross-venue market-sentiment proxy, not a Delta metric.

---

## 4. Recommendation

**Do not build a liquidation heatmap of either kind right now.**

Reasoning, weighing all of the above together:

1. **Delta itself provides nothing, at any price, for either
   definition** (§ 2). There is no "native" version of this feature —
   every path is either a different venue's data represented honestly as
   a proxy, or a paid third party's model of a venue this platform
   doesn't even trade through.
2. **The only genuinely free option (Binance's `forceOrder` stream) is
   definition (a) only, for a different venue, and is itself
   incomplete by design** (largest-per-symbol-per-second only). It would
   need to be clearly labeled a cross-market proxy on the dashboard, not
   presented as "this platform's liquidations."
3. **Every path to definition (b) — the modeled heatmap most people
   actually picture when they say "liquidation heatmap" — costs real,
   recurring money with no free tier at any provider checked**:
   Coinglass Professional at $699/mo is the cheapest verified path; a
   comparable Hyblock product exists at a similarly paid tier. Even the
   *weaker* definition (a) data from Coinglass (rather than the free
   Binance proxy) costs $299/mo minimum, and neither Coinglass tier
   permits the commercial use this platform would need below Standard.
4. **This session's own research thread has already, repeatedly, and
   rigorously found that open interest — the one real, already-ingested
   input a modeled heatmap (definition b) would be built from — carries
   no measurable held-out predictive value**, checked across three
   model classes (logistic regression, Random Forest, Gradient
   Boosting), five prediction horizons, and three market regimes (see
   `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`, `HORIZON_SWEEP_ASSESSMENT.md`,
   `REGIME_WALKFORWARD_ASSESSMENT.md`). A modeled liquidation heatmap
   built on top of OI plus an _assumed_ leverage distribution is a
   further, less-certain derivation of a quantity that already showed no
   signal — there is no positive evidence here to justify the
   above costs as a model-feature investment, only its plausible value
   as a **human-facing dashboard visualization** (traders do use these
   qualitatively, independent of whether they carry a statistically
   measurable predictive edge for this platform's own models).
5. Milestone 4's own remaining open threads (Epic 4.2's order-flow /
   microstructure capture, started under M4-E2-T1, and Milestone 5
   production hardening) are better-evidenced uses of engineering time
   than a paid third-party subscription for a feature this
   investigation found no free or native path to.

**If the decision is made to build it anyway** (e.g., a genuine
trader-facing UX priority independent of predictive-modeling value),
the fallback path, in priority order:

- **For definition (a) only, at zero recurring cost**: Binance's public
  `!forceOrder@arr` stream, clearly labeled as a market-wide (Binance)
  proxy, never as this platform's own exchange data. Architecturally
  this is a new, always-on WebSocket ingestion path (like the existing
  `DeltaWebSocketClient`, not like the periodic-REST `Connector`
  protocol the six existing connectors use — see § 1(a)) feeding a new
  aggregation store; out of scope for this spike, but worth naming since
  it is not a drop-in seventh connector.
- **For definition (b), or for Delta-branded liquidation-event data**:
  Coinglass, at Professional tier ($699/mo) for the modeled heatmap or
  Standard tier ($299/mo) for real events (still not Delta's own
  liquidations — Coinglass aggregates from the venues that do publish
  them, which does not include Delta). If a third-party connector is
  built for this, it follows the exact same `Connector` protocol
  (`app/connectors/base.py`'s `Protocol` + `ConnectorRegistry`) all six
  existing connectors already use — periodic REST polling, `RawDataPoint`
  shape or a dedicated table if the heatmap's own 2-D price/time payload
  doesn't fit that shape (mirroring Marketaux's own precedent for a
  connector whose real shape didn't fit the generic table). This
  platform already has a proven, fast pattern for exactly this kind of
  integration — a future task would not be starting from zero.

---

## Sources

- [Delta Exchange API: Introduction](https://docs.delta.exchange/) — REST/WebSocket reference, checked directly for liquidation endpoints/channels
- [Delta Exchange API Updates & Announcements](https://community.delta.exchange/c/api-updates-announcements/11) — scanned for any liquidation-feed announcement
- [Delta_client WebSocket guide (community)](https://github.com/kuldeepakkatwal/Delta_client/blob/main/docs/websocket-guide.md) — independent cross-check of channel/field lists
- [CoinGlass API — Get Liquidation Heatmap (Model1)](https://docs.coinglass.com/reference/liquidation-heatmap)
- [CoinGlass API — Get Futures Liquidation Order](https://docs.coinglass.com/reference/liquidation-order)
- [CoinGlass API docs — Liquidation Heatmap Model1 (GitHub mirror)](https://github.com/coinglass-official/coinglass-api-docs/blob/main/rest/Futures/Liquidation/liquidation-heatmap.md)
- [CoinGlass pricing](https://www.coinglass.com/pricing)
- [How to use Liquidation Heatmaps to assist trading? — CoinGlass](https://www.coinglass.com/learn/how-to-use-liqmap-to-assist-trading-en)
- [What Is a Liquidation Heatmap? The Complete Guide for Crypto Traders (2026) — Zipmex](https://zipmex.com/blog/what-is-a-liquidation-heatmap/)
- [How to Read Liquidation Maps in Crypto: 2026 Guide — DEXTools](https://www.dextools.io/tutorials/how-to-read-liquidation-maps-in-crypto-guide-2026)
- [Best Crypto Liquidation Heatmaps (2026) — CoinLobster](https://coinlobster.com/best-liquidation-heatmaps) — source for the heatmap-vs-real-events distinction and the "public exchanges do not publish entry price or leverage" framing
- [Liquidation Heatmap — Hyblock Academy](https://academy.hyblockcapital.com/tools/liquidation-levels-1)
- [Liquidation Heatmap API — Hyblock API Docs](https://docs.hyblockcapital.com/liquidation-heatmap)
- [Binance Open Platform — Liquidation Order Streams (USDⓈ-M Futures)](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams)
- [Binance Open Platform — All Market Liquidation Order Streams (Coin-M Futures)](https://developers.binance.com/docs/derivatives/coin-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams)
- [Binance Developer Community — Is there a websocket to stream liquidations?](https://dev.binance.vision/t/is-there-a-web-socket-to-stream-liquidations/44)
