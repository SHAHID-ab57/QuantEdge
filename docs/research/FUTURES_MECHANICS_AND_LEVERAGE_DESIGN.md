# Futures Mechanics and Leverage Design (M3-E5-T1)

**Status:** research and design spike. No application code was written or
changed. Date of all external checks: 2026-09-20.

**What this document is for.** Paper trading today is long-only, cash-only,
with no margin and no leverage, a deferral recorded when it was first built.
This document (1) records how Delta Exchange India's perpetual futures
actually work, from its own documentation and its live API, (2) designs how
short, margin and leveraged positions would fit the existing engine and its
risk mechanisms, and (3) lays out the leverage-sizing question as an
explicit choice for a human. It resolves none of the decisions in
[Part 5](#part-5-decisions-for-a-human).

## How to read the evidence

Every non-obvious claim below carries one of these tags. Trust them
differently.

| Tag           | Meaning                                                                                                      |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| **[docs]**    | Stated on a Delta documentation page (see [Sources](#sources)).                                              |
| **[api]**     | Read from Delta's public, unauthenticated REST API on 2026-09-20 (real call, real numbers).                  |
| **[derived]** | Worked out by me from a documented condition. Not quoted, and not confirmed by Delta unless a check says so. |
| **[code]**    | Read from this repository, with file and line.                                                               |
| **[data]**    | Measured from this platform's own stored data (dev database, read-only).                                     |
| **[unknown]** | Not documented on the pages read, and not measured. Needs verification before code depends on it.            |

**One limitation of the sources.** The Delta guide pages were retrieved with a
summarizing fetch tool, not read raw. The funding formula and the liquidation
condition were each independently checked numerically (below). The margin
scaling formulas and the initial-margin price rules by order type were **not**
independently confirmed and should be re-read on the page before code depends
on them.

## Summary

**The five findings that matter most:**

1. **The funding rate is in percent, and the platform's Live Market card
   shows it 100× too large.** Delta's `funding_rate` value is `0.01` when the
   rate is 0.01%. The card treats it as a fraction and multiplies by 100, so
   today it shows `+0.3172%` per 8h where the true figure is `+0.0032%`.
   Proven from Delta's own formula against 17 real funding times (mean error
   0.0009 percentage points reading it as percent, versus 0.53 reading it as a
   fraction). Any funding simulation would silently inherit this. **Existing
   bug, not fixed here.**
2. **Today's "drawdown" limit measures cash deployed, not loss.** It is
   evaluated on cash after a purchase, so buying more than `max_drawdown_pct`
   of cash halts the account with no price movement at all (the existing test
   `test_a_trade_that_breaches_drawdown_halts_the_account` asserts exactly
   this). Unrealized PnL is invisible to it. The risk limits cannot simply be
   extended to leverage; they have to be re-derived on equity and notional.
3. **A halted account cannot close or stop out, but liquidation cannot be
   halted.** The engine deliberately rejects every order, exits included, on a
   halted account. For a leveraged position that inverts the safety logic.
4. **Above about 19× leverage, the strategy's default 5% stop-loss can never
   fire before liquidation** (ETHUSD, using Delta's real margin parameters).
5. **Funding history is not persisted anywhere**, but Delta serves
   `FUNDING:`, `MARK:` and index candle history from the same public endpoint
   the platform's client already calls for ordinary candles. The gap is
   persistence and unit handling, not data availability.

**The decision that is not being made here:** how automated trades choose
leverage. The evidence in [Part 5, D1](#d1-how-automated-trades-choose-leverage)
shows the model's confidence carries no measurable relationship to being
right, so confidence-scaled leverage is **not offered** as an option.

**Recommended build order (not started):** fix the funding unit display first;
then mechanics (isolated margin, shorts, liquidation, funding) as one task;
automated-strategy integration as a separate, later task.

---

## Part 1: Delta's real futures mechanics

### 1.1 Contract parameters [api]

Read from `GET /v2/products/{symbol}` on `https://api.india.delta.exchange`
(the platform's own configured `delta_base_url`).

| Field                                | ETHUSD              | BTCUSD              | Note                                                                    |
| ------------------------------------ | ------------------- | ------------------- | ----------------------------------------------------------------------- |
| `contract_type`                      | `perpetual_futures` | `perpetual_futures` |                                                                         |
| `contract_value` (multiplier)        | 0.01 ETH            | 0.001 BTC           | 1 ETHUSD contract = 0.01 ETH                                            |
| `quoting_asset` / `settling_asset`   | USD / USD           | USD / USD           | **Linear (USD-margined)**, `notional_type: vanilla`, `is_quanto: False` |
| `initial_margin` (min, %)            | 0.5                 | 0.5                 | i.e. 200× max at small size                                             |
| `maintenance_margin` (min, %)        | 0.25                | 0.25                |                                                                         |
| `default_leverage`                   | 200                 | 200                 |                                                                         |
| `initial_margin_scaling_factor`      | 0.000004            | 0.0000025           | Slope for margin beyond the position threshold                          |
| `maintenance_margin_scaling_factor`  | 0.000002            | 0.00000125          |                                                                         |
| `max_leverage_notional` (USD)        | 100,000             | 100,000             | Probably the "position threshold" (see 1.2). **[unknown]** exact role   |
| `position_size_limit` (contracts)    | 162,683             | 125,000             |                                                                         |
| `position_notional_limit` (USD)      | 2,500,000           | 5,000,000           |                                                                         |
| `liquidation_penalty_factor`         | 0.2                 | 0.5                 | **[unknown]** meaning; not on the pages read                            |
| `insurance_fund_margin_contribution` | 5                   | 5                   | **[unknown]** meaning                                                   |
| `taker_commission_rate`              | 0.0005 (5 bps)      | 0.0005              | Paper fee is **10 bps** (`paper_trading_fee_bps`), about 2× real taker  |
| `maker_commission_rate`              | 0.0002 (2 bps)      | 0.0002              |                                                                         |
| `price_band` (%)                     | 5                   | 5                   | Limit-order price band. Irrelevant to market-order simulation           |
| `funding_method`                     | `mark_price`        | `mark_price`        |                                                                         |
| `product_specs.funding_clamp_value`  | 0.05                | 0.05                | Matches the documented ±0.05% clamp                                     |

**[unknown]:** whether GST or other levies apply on top of the commission
rates (India). Not checked. The paper fee (10 bps) versus the nominal taker
rate (5 bps) means the paper simulation is currently at least as costly as
the venue on fees, which is the conservative direction.

### 1.2 Margin [docs]

Source: Margin Explainer.

- **Modes.** Isolated margin: "margin is explicitly assigned to each
  position and is not shared across positions." Cross margin: "the entire
  balance in an account is available to be utilised." Cross margin has no
  per-position liquidation price: "it is not possible to compute
  liquidation prices for individual positions" (Cross Margin page).
- **Initial margin** by order type (the price used differs):
  - buy limit: `IM% × contracts × multiplier × limit bid price`
  - buy market: `IM% × contracts × multiplier × mark price`
  - sell limit: `IM% × contracts × multiplier × max(limit offer, best bid)`
  - sell market: `IM% × contracts × multiplier × max(mark price, best bid)`
- **Scaling.** Margin is flat up to a "Position Threshold". Beyond it,
  `IM% = IM%_min + Slope_IM × (size − threshold)` and
  `MM% = MM%_min + Slope_MM × (size − threshold)`.
- **Not stated on the page:** how unrealized PnL is computed, an explicit
  definition of leverage, and separate long and short formulas (the
  formulas are written generically).

For paper-account sizes (tens to a few thousand dollars of notional) the
threshold is never reached, so `IM = 0.5%` and `MM = 0.25%` apply. A first
build can simply **reject any order whose notional exceeds
`max_leverage_notional`** rather than model scaling.

### 1.3 Liquidation

**Trigger price is the mark price, not the last price** [docs]: "A position
goes into liquidation when Mark Price reaches the Liquidation Price of the
position."

**The defining condition** [docs]: "At Liquidation Price, the difference of
Position Margin minus Unrealized PnL of the position is equal to the
Maintenance Margin." Bankruptcy price: "the Unrealized Loss of a position
equal to the Position Margin." **Delta gives no closed-form liquidation
price formula** on the pages read.

**Derived formulas [derived]** for an isolated, linear (USD-margined)
position with entry `E`, initial margin ratio `IM = 1/leverage`, and
maintenance margin ratio `MM`:

| Side  | Bankruptcy price | Liquidation price         |
| ----- | ---------------- | ------------------------- |
| Long  | `E × (1 − IM)`   | `E × (1 − IM) / (1 − MM)` |
| Short | `E × (1 + IM)`   | `E × (1 + IM) / (1 + MM)` |

**Validation [derived, partial].** Delta's only worked example (Case 1) is
for an **inverse, BTC-margined** contract: long, entry 10,000, `IM` 1%,
`MM` 0.5%, stated bankruptcy 9,901 and liquidation 9,950. The inverse-contract
version of the same condition gives **9,900.99 and 9,950.25**, so my reading
of Delta's condition is right. That does **not** confirm the linear formulas
above, because Delta's examples are not linear. At 100× the two forms differ
by under $1, but they diverge at low leverage. The linear formulas are
therefore derived from a validated condition but unconfirmed by an example.
Treat them as needing one check against a real linear-contract liquidation
price before shipping.

**What happens at liquidation** [docs, Isolated Margin Liquidation page]:

- Position below the threshold: open orders are cancelled, an IOC market
  order is sent at the bankruptcy-price limit, any unfilled remainder is
  taken by the Liquidation Engine at the bankruptcy price. If the IOC fills
  better than the bankruptcy price, "a liquidation charge (equaling
  Maintenance Margin_min)" is deducted from the position margin.
- Position above the threshold: incremental liquidation to restore a 1%
  buffer to the mark price.
- **[unknown]:** insurance fund behaviour, auto-deleveraging, and the
  meaning of `liquidation_penalty_factor` are **not mentioned** on the page
  read. What a trader gets back (if anything) between the liquidation and
  bankruptcy prices is therefore not precisely specified.

**Numbers for ETHUSD [derived + api]** at the real minimum margins
(`MM = 0.25%`):

| Leverage | Initial margin | Long liquidation distance | Short liquidation distance | Default 5% stop reachable first? |
| -------- | -------------- | ------------------------- | -------------------------- | -------------------------------- |
| 1×       | 100%           | 100.00%                   | 99.50%                     | yes                              |
| 3×       | 33.33%         | 33.17%                    | 33.00%                     | yes                              |
| 5×       | 20.00%         | 19.80%                    | 19.70%                     | yes                              |
| 10×      | 10.00%         | 9.77%                     | 9.73%                      | yes                              |
| 19×      | 5.26%          | 5.03%                     | 5.00%                      | yes (barely)                     |
| 20×      | 5.00%          | 4.76%                     | 4.74%                      | **no, liquidated first**         |
| 50×      | 2.00%          | 1.75%                     | 1.75%                      | **no**                           |
| 200×     | 0.50%          | 0.25%                     | 0.25%                      | **no**                           |

The crossover is at initial margin 5.238%, about **19.1×**.

**Consistency with today's engine:** an unleveraged (1×) long has
`IM = 100%`, so its liquidation price is 0, meaning it can never be
liquidated. A 1× long is exactly today's position. Leverage generalizes the
existing model rather than replacing it.

### 1.4 Funding

**Rate formula** [docs, Perpetual Contracts Guide]:

```text
Funding Rate = Avg. Premium + clamp(Interest Rate − Avg. Premium, −0.05%, +0.05%)
Premium      = (Mark Price − Underlying Index Price) / Underlying Index Price
```

Premium is measured every minute and its 8-hour TWAP is used. The interest
rate is 0.01% per 8 hours. `product_specs.funding_clamp_value = 0.05` [api]
matches the clamp.

**Payment** [docs]: `Funding Payment = Current_Position_Value × Funding_Rate`,
where position value uses the current **Underlying Index Price**, not the
mark or last price. When the rate is positive, longs pay shorts; when
negative, shorts pay longs. "Delta Exchange does not charge any fees on
funding."

**Schedule.** One article says three fixed exchange times, 05:30, 13:30 and
21:30 IST, with a snapshot of all open positions at each. IST is UTC+5:30, so
these are 00:00, 08:00 and 16:00 UTC. The platform's own live data agrees:
its `funding_interval_seconds` for ETHUSD is 28,800 and its
`next_funding_time` is `2026-09-20T08:00:00Z` [data]. **A contradiction to
note:** a second article says the interval is "1 hour, 4 hours, 8 hours
(depending on the specific contract)." For ETHUSD the evidence says 8 hours,
but a per-market interval should be read from data, not hardcoded.

**Cap** [docs]: a "Funding Cap" exists and varies by contract, but the
value is **not stated** on the page read. **[unknown]**

#### The unit finding: `funding_rate` is in percent [data + api + derived]

Delta's ticker and its `FUNDING:ETHUSD` candles report values like
`0.003171`, `0.01`, `-0.0067`. To find their unit I computed the funding rate
from the documented formula using real history (5-minute mark candles from
`MARK:ETHUSD`, 5-minute index candles from `.DEETHUSD`, the 8-hour TWAP
premium before each funding time) and compared it to the published
`FUNDING:ETHUSD` value at 17 funding times (2026-09-14 to 2026-09-20):

| Reading of the published value | Mean absolute error vs. formula | Max error |
| ------------------------------ | ------------------------------- | --------- |
| **As percent** (0.01 = 0.01%)  | **0.0009** percentage points    | 0.0036    |
| As a fraction (0.01 = 1%)      | 0.5298 percentage points        | 0.9900    |

Three of the 17 funding times show exactly `0.010000`, which is the
documented 0.01% interest-rate floor (the premium sat inside the band where
the clamp makes the rate equal the interest rate). Read as a fraction that
would be 1% per 8 hours. The small remaining error under the percent reading
comes from using 5-minute bar closes instead of true per-minute premiums.

**Consequence for the platform [code]:**
`apps/dashboard/src/features/live-market/components/price-card.tsx` describes
`funding_rate` as "a signed fraction per funding interval (e.g. `-0.000116` =
shorts pay longs 0.0116%)" and renders `value × 100`. At the moment of
checking, Delta's ticker and the platform's own `/markets/ETHUSD/ticker` both
returned `0.003171652…`, which the card displays as **+0.3172%** when the true
rate is **+0.0032% per 8 hours**. The card overstates funding 100×. Nothing
else reads the value today, so there is no financial impact yet, but a funding
simulation built on it would charge 100× too much.

### 1.5 What is not documented, or not verified

| Item                                                                          | Status                                    |
| ----------------------------------------------------------------------------- | ----------------------------------------- |
| Closed-form liquidation price for a **linear** contract                       | derived, not confirmed by a Delta example |
| Meaning of `liquidation_penalty_factor`, `insurance_fund_margin_contribution` | [unknown]                                 |
| Insurance fund, auto-deleveraging behaviour                                   | [unknown], not mentioned on pages read    |
| What is returned between liquidation and bankruptcy price                     | [unknown]                                 |
| Exact funding cap per contract                                                | [unknown]                                 |
| Whether funding is settled to wallet or to position margin                    | [unknown]                                 |
| Behaviour when one order would flip a position through zero                   | [unknown]                                 |
| Whether GST or other levies apply to fees                                     | [unknown], not checked                    |
| Exact "position threshold" (vs `max_leverage_notional`)                       | [unknown]                                 |
| Whether hedge (two-sided) mode exists on this venue                           | [unknown], not checked                    |
| Margin scaling formulas and per-order-type IM prices                          | from a summarizing fetch, not re-verified |

---

## Part 2: Is the funding data already ingested sufficient?

**No, and here is precisely what is missing** (the task asked for this
explicitly).

What exists [code]: Delta's `funding_rate` WebSocket frame (`fr`, `fi`,
`nfr`) is parsed and normalized (`app/marketdata/normalizer.py:178`), held in
`MarketStateManager` **in memory**, and served over `/api/v1/ws/market` and
`/markets/{symbol}/ticker`. Persisted: only `markets.funding_interval_seconds`
and `markets.funding_method`, both static metadata [data: the only database
columns containing "fund" are those two].

| Need for realistic funding simulation                          | Available today?                                                |
| -------------------------------------------------------------- | --------------------------------------------------------------- |
| The rate applied at each funding time                          | **No.** Live value only; lost on restart; no history table.     |
| History, to backtest or catch up after downtime                | **No.** Not persisted.                                          |
| Index price at the funding time (the payment formula needs it) | Partly. `spot_price` is on `TickerEvent`, but is not persisted. |
| Mark price (needed for liquidation and mark-to-market)         | Live only, in `TickerEvent.mark_price`. Not persisted.          |
| Correct unit handling                                          | **No.** The one consumer misreads it by 100× (finding 1).       |

**What Delta offers that makes this cheap [api]:** the same public endpoint
the platform already calls for ordinary candles
(`DeltaClient.get_candles`, `CANDLES_PATH = "/v2/history/candles"`) also
serves:

- `FUNDING:ETHUSD` (the authoritative funding rate history; 72 hourly rows
  returned for a 3-day window, 1,723 five-minute rows for 6 days),
- `MARK:ETHUSD` (mark price history),
- `.DEETHUSD` (the spot index, named in the product's `spot_index.symbol`).

So the missing piece is **persistence and unit handling**, not a new data
source. Live paper trading can settle funding from the authoritative candle
shortly after each funding time; catch-up after downtime and future
backtesting work from the same history.

---

## Part 3: What the existing engine assumes, and where

Everything below is a **[code]** finding. The long-only assumption lives in the
schema and service, not in the fill maths.

| Concern                       | Where                                                                                      | Assumption                                                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Position sign                 | `app/models/paper_trading.py:313`, `CheckConstraint("quantity >= 0")`                      | A position is a non-negative quantity; there is no short and no side column                                                            |
| Order sides                   | `models/paper_trading.py:50`, `ORDER_SIDES = ("buy", "sell")`                              | A sell only ever reduces a held long                                                                                                   |
| Sell path                     | `services/paper_trading.py:409`, `InsufficientPositionError` when `quantity > held`        | Selling more than held is rejected, so no short can be opened                                                                          |
| Cash accounting               | `services/paper_trading.py:361` `new_balance = balance - total_cost`                       | A buy spends full notional in cash; `balance >= 0` (`models:157`)                                                                      |
| Realized PnL                  | `services/paper_trading.py:410-413`, `(fill − avg_entry) × qty − fee`                      | Long formula only                                                                                                                      |
| Position-size limit           | `services/paper_trading.py:419-429`                                                        | `qty × last_price` as a % of **cash** `balance`                                                                                        |
| Exposure limit                | `services/paper_trading.py:431-440`, `_total_exposure_value` (line 1023)                   | Sum of position values as a % of **cash** `balance`                                                                                    |
| Drawdown / halt               | `services/paper_trading.py:442`, `_apply_drawdown_tracking` (line 1051)                    | `new_balance` (cash after the trade) against `peak_balance`. **Cash, not equity**                                                      |
| Halt semantics                | `services/paper_trading.py:328` and `:557`                                                 | A halted account rejects **every** order, including triggered exits ("a halted account accepts no orders, including a triggered exit") |
| Stop-loss / take-profit       | `paper_trading/monitor.py:219-221`, `_crossed_threshold`; `services/paper_trading.py:1066` | `price <= stop` and `price >= take`; stop below price, take above. Long only                                                           |
| Price used for triggers/fills | `paper_trading/pricing.py:resolve_current_price`; `monitor.py` `_on_ticker_updated`        | **Last price** (ticker `last_price`, then trade). Not mark price                                                                       |
| Automated strategy            | `services/paper_trading_strategy.py:62, 357`                                               | "never a short: this platform is long-only, unconditionally". Bearish + flat is a logged `no_action`                                   |
| Fill model                    | `paper_trading/pricing.py:110-131`, `apply_fill_model`                                     | **Already direction-symmetric:** a buy fills higher, a sell fills lower. Correct for opening or covering a short                       |

**The fill model needs no change for shorts.** Opening a short is a sell
(fills lower, against the trader), covering is a buy (fills higher). The
long-only constraint is entirely in the schema, the service branches, the
monitor, and the strategy.

**Existing behaviour worth stating precisely, because the extension
interacts with it:**

- The drawdown limit is evaluated on cash after a purchase. The existing test
  buys 2 units at a flat price of 1,000 with a 10,000 balance and asserts the
  account is halted because cash fell "a 20.03% drop from the $10,000 peak"
  (`tests/paper_trading/test_service.py:811-843`). This is documented in the
  test as "this feature's own spec", so it is a deliberate choice, but it
  means "drawdown" currently means capital deployed.
- With default limits (position 10%, exposure 50%, drawdown 20%, all
  measured against cash), two ordinary 10%-of-cash purchases already exceed
  the drawdown limit. The live strategy never hit this because it holds one
  small position at a time (verified: the dev database's three accounts are
  none halted, and the active account is flat).

---

## Part 4: Design

**Principles.**

1. **Mirror the long side's discipline exactly:** real slippage against the
   trader, real fees, price source and staleness recorded, never a perfect
   fill.
2. **One code path.** As with the strategy ("just another caller of
   `place_order`"), shorts and leverage go through the same order path, the
   same atomic `try_apply_trade_effects` guard, and the same audit trail.
3. **Conservative where Delta is unspecified.** Where Part 1.5 says
   [unknown], choose the outcome that is worse for the trader, and record
   that it was a choice.
4. **Generalize, don't fork.** A 1× long must remain exactly today's
   behaviour (see 1.3: a 1× long is a position with initial margin 100%).

### 4.1 Margin model: isolated only, first

Isolated margin has a well-defined per-position liquidation price. Cross
margin has none by Delta's own statement, and would need the whole-account
collateral ratio (`MMR > 100%`), a materially larger design. **Recommend
isolated only for the first build** (see D5).

### 4.2 Data model (conceptual, no code)

- **`PaperPosition`:** add `side` (`long`/`short`), `leverage`, `margin`
  (position margin posted), `liquidation_price`. Keep `quantity >= 0` as a
  **magnitude**. One position per `(account, symbol)` (net, one-way mode),
  which the existing unique constraint already enforces. Legacy rows migrate
  to `side=long, leverage=1, margin = quantity × average_entry_price`.
- **`PaperAccount`:** `balance` becomes **available cash** (unchanged
  meaning for 1× longs). Add derived **equity** =
  `balance + Σ(position margin + unrealized PnL at mark)`. Add
  `max_leverage` as a per-account limit.
- **`PaperOrder`:** add `leverage` and `margin_applied`; allow
  `trigger_reason = 'liquidation'` alongside `stop_loss` and `take_profit`;
  add a `reduce_only` flag.
- **New table for funding:** one row per `(account, symbol, funding_time)`
  with the rate used, index price, position value, signed payment and the
  source of the rate. The unique key makes settlement idempotent.
- **New table for funding-rate history:** ingested from `FUNDING:`, `MARK:`
  and index candles (Part 2), with the percent-to-fraction conversion done
  **once, at ingestion, with a test** based on the first-principles check in
  1.4.

### 4.3 Order semantics

One-way (net) mode. A sell against a flat or short position **opens or adds
to a short**; a buy against a short **reduces or covers** it. **An order that
would flip a position through zero in one step is rejected** (the caller
sends a reduce-to-zero and then a new opening order). Delta's behaviour here
is [unknown], and rejecting is the conservative, auditable choice.

### 4.4 Fills and PnL

Short realized PnL is `(average_entry − fill_price) × quantity − fee`, the
mirror of the long formula. Slippage direction needs no change (1.3 above).
Fees are `fee_bps` of the fill's notional as today. **Note:** the paper fee
(10 bps) is about twice Delta's nominal taker rate (5 bps); leaving it is
conservative, changing it is a separate decision.

### 4.4a Margin and leverage accounting

Opening a position of notional `N` at leverage `L` posts margin `N / L` from
available cash (plus the fee). `balance >= 0` then means "enough available
cash to post the margin", which is the same check as today at `L = 1`.
Per-position leverage is fixed at open in the first build (no changing
leverage on an open position). There is no margin top-up and no cross
collateral in isolated mode. **Initial margin uses the mark price** for
market orders, per Delta's rule (1.2).

### 4.5 Liquidation model

- **Monitor on mark price.** `TickerUpdated` events already carry
  `mark_price` (`app/marketdata/models.py:75`). The existing
  stop-loss/take-profit monitor is event-driven on `last_price`; liquidation
  is a third trigger on `mark_price`. **If no mark price is available,** fall
  back to last price and record that the trigger used a fallback.
- **Trigger** when mark reaches the liquidation price (formulas in 1.3).
- **Fill** at the liquidation engine's price using the wider triggered
  slippage (`paper_trading_triggered_slippage_bps`), never at the stale
  threshold, the same principle the monitor already documents for gaps.
- **Loss is capped at the posted margin** (isolated margin: the trader
  cannot lose more than the margin assigned to that position). If the price
  gapped through the bankruptcy price, record a `gapped_through_bankruptcy`
  flag; the excess is the venue's problem in reality (insurance fund or
  auto-deleveraging, [unknown]) and is not charged to the paper account.
- **Residual margin.** Delta's page implies something may be returned
  between the liquidation and bankruptcy prices ([unknown]). **Conservative
  choice: forfeit the full posted margin.** Record it as a choice.
- **Verification path.** Because the linear liquidation formula is derived,
  the build should include one check of the computed liquidation price
  against a real linear-contract figure before shipping.

### 4.6 Funding simulation

- **When.** At each funding time (per market, from `funding_interval_seconds`;
  ETHUSD is 00:00, 08:00, 16:00 UTC), snapshot every account's open position
  in that market.
- **Amount.** `signed_payment = position_value_at_index × funding_rate/100`,
  charged to longs and credited to shorts when the rate is positive, the
  reverse when negative. Fees on funding: none (Delta charges none).
- **Rate source.** Prefer the **authoritative `FUNDING:` candle** for that
  time, fetched shortly after the funding time (the rate is published, not
  estimated). Fall back to the last live WebSocket value before the boundary,
  flagged as an estimate. This makes settlement both correct and catch-up
  safe after downtime.
- **Where the payment lands** (wallet or position margin) is [unknown]. The
  conservative choice is to charge available cash and, if that is
  insufficient, position margin, which moves the liquidation price. Record
  the choice.
- **Idempotency.** The `(account, symbol, funding_time)` key means a re-run
  or catch-up never double-charges.
- **Cost scale for intuition [derived].** On 10,000 USD notional a rate of
  0.01% per 8h is $1.00 per interval, $3.00 per day. Read as a fraction the
  same number would be $100 per interval, which is why the unit fix comes
  first.

### 4.7 Interaction with every existing risk mechanism

This is the part the task asked to be re-derived rather than extended. A key
observation first: **the default limits already cap total notional far below
account equity** (position 10%, exposure 50%, both measured on cash).
Applied to notional, they would mean leverage changes only how much cash is
locked, not how much market exposure the account holds. Whether to allow
account-level notional above equity at all is therefore a separate
decision (D1, D7).

| Mechanism                              | What it measures today                            | Problem under shorts/leverage                                                                                | Proposed                                                                                                                  |
| -------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `max_position_size_pct`                | `qty × price` as % of **cash**                    | Cash falls as margin is posted, and notional is what carries risk                                            | Position **notional at mark** as % of **equity**                                                                          |
| `max_exposure_pct`                     | Σ position values as % of **cash**                | Same; and it ignores side                                                                                    | Σ \|notional\| as % of **equity**. This becomes the account-level effective-leverage cap                                  |
| New: `max_leverage`                    | (does not exist)                                  | Needed so per-position leverage has a ceiling independent of margin availability                             | Per-account cap on per-position leverage                                                                                  |
| New: margin check                      | (does not exist)                                  | A leveraged order must be fundable                                                                           | Available cash must cover initial margin plus fee                                                                         |
| `max_drawdown_pct` + halt              | **Cash** after a trade vs. peak cash              | Cash falls whenever margin is posted, with no loss. Unrealized loss is invisible. Worse with leverage        | **Equity** (marked to market) vs. peak equity. **A deliberate semantic change for existing accounts**, see D3             |
| `trading_halted` (kill switch)         | Rejects **every** order, exits included           | A halted leveraged account could not close or stop out, yet liquidation, on the exchange side, still happens | Halt blocks **new risk only**; reduce-only orders and triggered exits stay allowed. Liquidation is never blocked (see D4) |
| Stop-loss                              | `price <= stop`, stop set below price (long only) | Wrong direction for a short; unreachable if beyond the liquidation price                                     | Direction by side; **reject a stop beyond the liquidation price** at set-time; recommend a minimum buffer                 |
| Take-profit                            | `price >= take`, above price (long only)          | Wrong direction for a short                                                                                  | Direction by side                                                                                                         |
| Trigger ordering                       | Stop before take-profit                           | A third trigger, on a different price (mark vs. last)                                                        | Fixed order: **liquidation first**, then stop-loss, then take-profit; deterministic, recorded in `trigger_reason`         |
| Automated strategy (`strategy_*`)      | Long only; bearish + flat is `no_action`          | Would newly open shorts if unchanged                                                                         | **Not integrated in this design.** Separate, later task and separate decision (D2)                                        |
| Atomic guard `try_apply_trade_effects` | Compares `balance` and `trading_halted`           | New state (margin, funding) must join the same guard, or races reappear                                      | Extend the expected-state comparison; one guarded update per order                                                        |

**Why liquidation outranks the stop.** A stop is a paper order the simulator
executes; liquidation is the exchange acting on the account regardless of
what the account intended. The two use different prices (last for the stop,
mark for liquidation), so a fast move can cross both on one tick. The rule
that liquidation is checked first is the conservative one, because it is the
outcome the real venue would impose.

**The kill switch, restated.** Today "kill switch" is the drawdown halt
(`trading_halted`) plus the per-account `strategy_enabled` opt-in. Neither
flattens positions. Under leverage, the halt must stop _adding_ risk while
still permitting risk-reducing exits, or it makes the account less safe.
Whether a breach should also _flatten_ the account is a real choice (D4).

### 4.8 What changes at the API and UI (scope, not design)

Order requests gain `leverage` and `reduce_only`; position and summary
responses gain `side`, `leverage`, `margin`, `liquidation_price`, `equity`;
the health/risk summary gains equity and effective leverage. The Paper
Trading page needs a side and leverage selector and a visible liquidation
price. Audit entries must record leverage and margin (the existing audit
trail already attributes orders to a user). These are sized in the build
tasks below, not designed here.

### 4.9 Proposed split of the build (not started)

1. **Prerequisite (small, independent):** fix the funding unit display, and
   add the `FUNDING:`/`MARK:`/index ingestion with the unit conversion at the
   boundary and its first-principles test.
2. **Mechanics:** isolated margin, shorts, liquidation on mark price,
   funding settlement, equity-based limits, halt semantics, and the schema
   migration for legacy rows. Manual orders only.
3. **Strategy integration (later, separately scrutinized):** whether and how
   the automated strategy may short or use leverage, after D1 and D2 have
   explicit answers.

---

## Part 5: Decisions for a human

These are choices, not defaults. Nothing above is built until they have
answers.

### D1: How automated trades choose leverage

**Not offered: sizing leverage from the model's own confidence.** The
evidence, all from this project's own measurements:

- **No model class, horizon, or regime shows directional skill.** ROC-AUC is
  about 0.5 everywhere. Regime walk-forward (`REGIME_WALKFORWARD_ASSESSMENT.md`):
  0.512, 0.507, 0.495 across an uptrend (+100%), a downtrend (−28%) and a
  range, every 95% interval including 0.5, with the model predicting "down"
  99.8%+ of the time in all three. Horizon sweep
  (`HORIZON_SWEEP_ASSESSMENT.md`): no horizon from 1h to 48h clears 0.5 once
  overlap is corrected with a block bootstrap. Connector features
  (`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`): no feature adds measurable value
  under logistic regression, Random Forest or Gradient Boosting.
- **The confidence score in particular does not track accuracy [data].** Over
  **8,126 graded classification predictions** in the dev database:
  mean confidence **0.889** (sd 0.131) against accuracy **0.460**;
  Spearman correlation between confidence and being correct **−0.020**
  (95% bootstrap interval −0.041 to +0.002); **91.7%** of predictions clear
  the strategy's default 65% confidence gate, so the gate barely filters
  anything. In the backtest-only subset (5,546) the correlation is +0.010
  (−0.016 to +0.036). In the live-only subset (2,580) it is −0.052, with
  accuracy in the highest-confidence bins of 0.366 and 0.282 against 0.488
  in a middle bin.
- **Caveat that must not be dropped.** These predictions are sequential and
  heavily overlapping, so a per-row bootstrap **understates** uncertainty,
  the same pseudo-replication problem the horizon sweep found. The live
  subset's "significantly negative" correlation must **not** be read as
  genuine inverse skill. The defensible reading is narrower and sufficient:
  there is **no evidence of the positive relationship** that confidence-sized
  leverage would require, and no configuration where confidence was
  informative.
- **Leverage amplifies costs as well as calls.** Round-trip cost under the
  paper model (5 bps slippage plus 10 bps fee, each side) is 0.30% of
  notional and therefore **0.30% × leverage of posted margin**: 0.9% of
  margin at 3×, 3.0% at 10×, 6.0% at 20×, on a trade with zero expected edge.

Given that, the two real options are:

**Option 1: volatility-targeted.** Leverage is `target_vol / realized_vol`,
independent of the model's confidence. **What it does on ETHUSD [data]**
(22,967 hourly candles, 2024-02-06 to 2026-09-20; 7-day realized volatility,
annualized: 5th percentile 37%, median 60%, 95th percentile 101%):

| Target vol | Median leverage | 5th–95th percentile | Share of time above 1× | Above 3× |
| ---------- | --------------- | ------------------- | ---------------------- | -------- |
| 20%        | 0.33×           | 0.20–0.54×          | 0%                     | 0%       |
| 40%        | 0.67×           | 0.40–1.08×          | 8%                     | 0%       |
| 60%        | 1.00×           | 0.60–1.62×          | 50%                    | 0%       |
| 80%        | 1.34×           | 0.80–2.16×          | 83%                    | 1%       |
| 100%       | 1.67×           | 0.99–2.70×          | 95%                    | 2%       |

The important consequence: at any realistic target, ETH's volatility means
this option **mostly de-leverages**, and reaching 3× as a median would need a
target above 180% volatility. It is closer to a position-size scaler than a
leverage engine. Its real property is that it keeps exposure lower when
markets are wilder. It adds moving parts (a volatility estimator, a target
to choose, a data dependency) and it creates **no edge**.

**Option 2: a fixed, human-set cap.** Automated trades always use one
conservative level; variable leverage is available only for manual trades a
person places and reviews. How exposed each level is to liquidation, on real
ETHUSD history [data] (share of hourly entries that would have been
liquidated within the holding window; isolated margin; hourly intrabar
high/low, with last price standing in for mark, so treat as approximate):

| Leverage | Long, 4h | 24h   | 72h   | Short, 4h | 24h   | 72h   | Liquidation distance |
| -------- | -------- | ----- | ----- | --------- | ----- | ----- | -------------------- |
| 2×       | 0.0%     | 0.0%  | 0.0%  | 0.0%      | 0.0%  | 0.0%  | ~49.9%               |
| 3×       | 0.0%     | 0.0%  | 0.2%  | 0.0%      | 0.0%  | 0.3%  | ~33.2%               |
| 5×       | 0.0%     | 0.3%  | 2.1%  | 0.0%      | 0.2%  | 1.1%  | ~19.8%               |
| 10×      | 0.1%     | 2.5%  | 11.8% | 0.1%      | 2.0%  | 10.4% | ~9.8%                |
| 20×      | 1.7%     | 15.8% | 35.9% | 1.2%      | 13.8% | 36.2% | ~4.8%                |
| 50×      | 16.5%    | 51.8% | 70.0% | 15.2%     | 51.8% | 73.1% | ~1.75%               |

A cap of 1× is a legitimate value of this option (it means automation does
not use leverage at all, only, at most, shorts).

**The framing point.** Neither option manufactures an edge the research says
does not exist. Both only bound the damage. With no demonstrated skill there
is no leverage level at which the expected result is positive; the strongest
argument for _any_ leverage is not returns but (a) letting a person practice
manual leveraged trades against realistic mechanics, and (b) mechanics
realism. That favors Option 2 with a low or 1× cap for automation.

**My lean, flagged as a lean and not a decision:** Option 2, cap at 1× for
automated trades until a validated edge exists (2× to 3× if some leverage is
wanted, given the near-zero 24-hour liquidation rates above), with variable
leverage for manual trades only. Option 1 can be revisited later; its main
merit (lower exposure in high volatility) is achievable without leverage at
all by scaling position size, and at ETH's volatility it would seldom exceed
1× anyway.

### D2: May the automated strategy open shorts at all?

Separate from leverage, and not named in the task. Today a bearish call on a
flat account is a logged `no_action`; the strategy participates only on
"up" calls. Allowing shorts roughly doubles the situations in which a
no-skill model trades, and each trade costs 0.30% of notional round trip. The
regime study found the live-type model is a near-constant "down" predictor
(99.8%+ of calls), which under a short-enabled strategy would mean **almost
always short**. Decide separately, and after the manual mechanics exist.

### D3: What should "drawdown" measure?

Cash (today), or equity marked to market. Under margin, cash-based drawdown
halts an account merely for posting margin. Equity-based drawdown is the
correct risk measure but **changes behaviour for existing accounts**: some
positions that would halt today would not, and unrealized losses would newly
count. Options: unify on equity for all accounts; or keep the legacy
cash-based rule for 1×-only accounts and use equity for accounts that use
margin. Unifying is simpler and more honest; it is a behaviour change that
should be announced.

### D4: What does the kill switch do on a leveraged account?

Halt new risk only (allow reduce-only and triggered exits), or also flatten
every position when the drawdown limit is breached. Halting without allowing
exits is unsafe under leverage (finding 3). Flattening is stronger protection
but is a forced, fee-paying, slippage-paying action taken on the account's
behalf. Present as a choice; a reasonable default is "halt new risk, allow
exits, alert", with flattening as an opt-in.

### D5: Isolated margin only, or cross margin too?

Recommend isolated only for the first build: it has a per-position
liquidation price, which the stop-loss and buffer logic depends on. Cross
margin has no per-position liquidation price by Delta's own statement and
needs an account-level collateral ratio.

### D6: On liquidation, forfeit the full margin or model a residual?

Delta's page implies a residual may exist between liquidation and bankruptcy
prices but does not specify it. **Full forfeiture is the conservative
choice and never generous**, consistent with the fill discipline. The
alternative needs data Delta did not document.

### D7: May account-level notional exceed equity?

The default limits (position 10%, exposure 50%) keep total notional well
under equity. If those limits are re-expressed on notional (Part 4.7), then
**leverage does not increase the account's market exposure at all**; it
changes only how much cash is locked as margin and how close a liquidation
price sits. True account-level leverage above 1× requires raising
`max_exposure_pct` above 100% deliberately. This is the decision that
actually determines whether the account can lose more than it would today, so
it should be made explicitly and separately from D1.

---

## Part 6: Existing issues found during this investigation

None were fixed (this task is no-code). Listed in the order they should be
addressed.

| #   | Finding                                                                                              | Evidence                                                | Severity                                                  |
| --- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------- |
| 1   | Live Market card shows funding **100× too large** (`funding_rate` is percent, treated as a fraction) | Part 1.4; `price-card.tsx:68-80`                        | Display only today; blocks any funding simulation         |
| 2   | "Drawdown" measures cash deployed, not loss; halts on buying alone                                   | `services/paper_trading.py:1051`; `test_service.py:811` | Latent; not hit by the live strategy (one small position) |
| 3   | A halted account cannot close, and cannot honour a stop-loss, so it stays exposed                    | `services/paper_trading.py:328, 557`                    | Latent for 1×; unsafe under leverage                      |
| 4   | Funding rate is not persisted, so there is no history and it is lost on restart                      | Part 2                                                  | Blocks funding simulation and its backtest                |
| 5   | Paper fee (10 bps) is about 2× Delta's nominal taker rate (5 bps)                                    | Part 1.1                                                | Conservative direction; a separate decision               |
| 6   | The `price-card.tsx` comment's example (`-0.000116` = 0.0116%) is off by the same 100×               | `price-card.tsx:67-70`                                  | Documentation error, same root cause as #1                |

## Part 7: What was not verified

- A liquidation price for a **linear** contract from Delta itself (only the
  inverse worked example was reproduced).
- The exact per-contract funding cap, the insurance fund, auto-deleveraging,
  and the meaning of `liquidation_penalty_factor`.
- Whether funding settles to wallet or to position margin.
- That the margin scaling formulas and the initial-margin price rules are
  transcribed correctly (retrieved through a summarizing tool).
- Whether GST applies on fees.
- Any behaviour on a real Delta account. **No authenticated call was made and
  no real order was placed.** All API calls were public, read-only endpoints.
- The liquidation-frequency table uses last-price intrabar extremes as a
  stand-in for mark price and enters at each hourly close without slippage.

The recommended way to close the liquidation-formula gap is one small
comparison against a real linear-contract liquidation price from the Delta
UI, before any code depends on the derived formulas.

## Reproducing the measurements

All measurements were made read-only. The analysis scripts were run from a
scratch directory and are not part of the repository. The queries and calls
they used:

- **Contract parameters:** `GET https://api.india.delta.exchange/v2/products/ETHUSD`
  and `/BTCUSD`.
- **Live funding and mark:** `GET /v2/tickers/ETHUSD`.
- **Funding, mark and index history:**
  `GET /v2/history/candles?resolution=5m&symbol=FUNDING:ETHUSD` (and
  `MARK:ETHUSD`, `.DEETHUSD`), start and end as Unix seconds.
- **Funding unit test:** for each funding time, the 8-hour TWAP of
  `(mark − index) / index` over 5-minute bars, then the documented formula
  with a 0.01% interest rate and ±0.05% clamp, compared to the published
  `FUNDING:` value read both ways.
- **Confidence calibration:** `predictions` where `graded_at`, `confidence`
  and `is_correct` are non-null and `model_kind = 'classification'`;
  Spearman correlation with a 2,000-sample bootstrap.
- **Volatility and liquidation frequency:** ETHUSD 1h candles from
  `candles` joined to `markets`; 168-hour rolling realized volatility;
  sliding-window minimum low and maximum high over the next 4, 24 and 72
  hours against the liquidation distances in 1.3.

## Sources

Delta Exchange India documentation and API (retrieved 2026-09-20):

- Margin Explainer:
  <https://guides.delta.exchange/delta-exchange-india-user-guide/trading-guide/margin-explainer/margin-explainer>
- Liquidation of Isolated Margin Positions:
  <https://guides.delta.exchange/delta-exchange-india-user-guide/trading-guide/margin-explainer/margin-explainer/liquidation-of-isolated-margin-positions>
- Cross Margin:
  <https://guides.delta.exchange/delta-exchange-india-user-guide/trading-guide/margin-explainer/cross-margin>
- Perpetual Contracts Guide (funding formula and payment):
  <https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs>
- Update on Funding Exchange Schedule for Perpetual Contracts:
  <https://www.delta.exchange/support/solutions/articles/80001183756-update-on-funding-exchange-schedule-for-perpetual-contracts>
- What Is Funding in Perpetual Contracts:
  <https://www.delta.exchange/support/solutions/articles/80001177906-what-is-funding-in-perpetual-contracts->
- Are There Any Limits on Funding:
  <https://www.delta.exchange/support/solutions/articles/80001177909-are-there-any-limits-on-funding->
- API base <https://api.india.delta.exchange> (public endpoints
  `/v2/products/{symbol}`, `/v2/tickers/{symbol}`, `/v2/history/candles`);
  API documentation at <https://docs.delta.exchange/>.

Project research cited: `docs/research/REGIME_WALKFORWARD_ASSESSMENT.md`,
`docs/research/HORIZON_SWEEP_ASSESSMENT.md`,
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`.
