# Paper Trading — Complete Feature Guide

## Document Information

**Feature:** Paper Trading — a virtual trading account that places simulated
market orders against real prices, tracks positions, and computes PnL.
Milestone 3, task `M3-E1-T1`. Long-only, market orders only — no margin, no
shorting, no leverage, no automation, no prediction-driven trading (each is a
separate, later task).

**Scope of this document:** everything that exists in the backend, everything
that exists in the frontend (including every single field rendered on the
page), and step-by-step manual test instructions with real values. This is
the same depth/format convention as [`docs/ml-pipeline/QAReference.md`](../ml-pipeline/QAReference.md)
(field-by-field reference) and [`docs/ml-pipeline/MLPipelineGuide.md`](../ml-pipeline/MLPipelineGuide.md)
(manual walkthroughs), combined into one file because this feature is small
enough not to need the two-document split those six subsystems needed.

**Status:** written 2026-09-04, read directly from source on the `feat/setup`
branch. Every file path, field name, default value, and error code below was
verified against the actual code — nothing here is aspirational. Cross-reference:
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) § "Paper Trading" (design rationale),
[`docs/api/API.md`](../api/API.md), `services/api/TESTING.md`.

**Prerequisites for manual testing:** Postgres running with at least one
market synced and at least one candle stored for it (`ETHUSD`/`BTCUSD` — see
[`docs/ml-pipeline/MLPipelineGuide.md`](../ml-pipeline/MLPipelineGuide.md) § 4
for how to import real historical data if you have none), the API running
(`uv run fastapi dev app/main.py` from `services/api`), and the dashboard
running (`pnpm dev` from `apps/dashboard`, default `http://localhost:3000`).

---

## Table of Contents

1. [Backend](#1-backend)
2. [Frontend](#2-frontend)
3. [Automated tests](#3-automated-tests)
4. [Manual test scenarios — real values, step by step](#4-manual-test-scenarios--real-values-step-by-step)
5. [Known gaps / out of scope](#5-known-gaps--out-of-scope)

---

## 1. Backend

### 1.1 Module layout

```text
services/api/app/paper_trading/            Framework/database-free domain logic
├── base.py                                FillQuote / FillResult dataclasses
├── errors.py                              Domain error types
└── pricing.py                             resolve_current_price / apply_fill_model

services/api/app/models/paper_trading.py   SQLAlchemy ORM: PaperAccount, PaperOrder, PaperPosition
services/api/app/repositories/paper_trading.py
                                            PaperAccountRepository, PaperOrderRepository,
                                            PaperPositionRepository
services/api/app/services/paper_trading.py PaperTradingService — the orchestration layer
services/api/app/schemas/paper_trading.py  Pydantic request/response DTOs
services/api/app/api/v1/endpoints/paper_trading.py
                                            The 5 REST endpoints
services/api/app/dependencies/paper_trading.py
                                            get_paper_trading_service() DI wiring
services/api/alembic/versions/20260904_7a3254fe72af_add_paper_trading_schema.py
                                            The migration that creates all 3 tables
```

Same layering discipline as every other domain on this platform: routers
never touch SQL — they call `PaperTradingService`, which calls the
repositories. `app/paper_trading/` itself has no SQLAlchemy or FastAPI import
at all; it is pure pricing/fill-model logic, unit-tested in isolation.

### 1.2 Configuration settings (`app/core/config.py:114-131`)

| Setting                                       | Default | Purpose                                                                             |
| --------------------------------------------- | ------- | ----------------------------------------------------------------------------------- |
| `paper_trading_slippage_bps`                  | `5`     | Basis points the fill price moves _against_ the trader off the resolved quote.      |
| `paper_trading_fee_bps`                       | `10`    | Basis points of the fill's own notional (`fill_price × quantity`) charged as a fee. |
| `paper_trading_stale_price_threshold_seconds` | `300`   | Age (seconds) beyond which a resolved quote is marked `is_stale_price=true`.        |
| `paper_trading_accounts_default_limit`        | `20`    | Default page size, `GET .../accounts`.                                              |
| `paper_trading_accounts_max_limit`            | `100`   | Max page size, `GET .../accounts`.                                                  |
| `paper_trading_orders_default_limit`          | `20`    | Default page size, `GET .../accounts/{id}/orders`.                                  |
| `paper_trading_orders_max_limit`              | `100`   | Max page size, `GET .../accounts/{id}/orders`.                                      |

None of these are hardcoded anywhere in the pricing/service/test code — every
test that asserts an exact slippage/fee amount does so against these
settings' actual values, not a copy-pasted constant.

### 1.3 Database schema

Three tables, migration `7a3254fe72af`. Every model also carries `id` (UUID
primary key, `uuid.uuid4` default) and `created_at`/`updated_at`
(`TimestampMixin`, timezone-aware UTC, `server_default=func.now()`) — omitted
from the tables below since they're identical across every model on this
platform.

#### `paper_accounts` (`PaperAccount`)

| Column             | Type              | Nullable | Constraint  | Meaning                                                                        |
| ------------------ | ----------------- | -------- | ----------- | ------------------------------------------------------------------------------ |
| `name`             | `String(200)`     | Yes      | —           | Optional label, user-supplied.                                                 |
| `starting_balance` | `Numeric(38, 18)` | No       | `>= 0`      | Cash the account opened with; never changes after creation.                    |
| `balance`          | `Numeric(38, 18)` | No       | `>= 0`      | Current cash. A buy decreases it, a sell increases it; never negative.         |
| `realized_pnl`     | `Numeric(38, 18)` | No       | default `0` | Cumulative realized gain/loss across every order this account has ever placed. |

#### `paper_orders` (`PaperOrder`)

| Column              | Type              | Nullable | Constraint                               | Meaning                                                                                                     |
| ------------------- | ----------------- | -------- | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `account_id`        | UUID FK           | No       | `ON DELETE CASCADE`, indexed             | Owning account.                                                                                             |
| `symbol`            | `String(50)`      | No       | indexed                                  | Market symbol traded (e.g. `ETHUSD`).                                                                       |
| `side`              | `String(4)`       | No       | `IN ('buy', 'sell')`                     | Order direction.                                                                                            |
| `quantity`          | `Numeric(38, 18)` | No       | `> 0`                                    | Base-asset units filled.                                                                                    |
| `raw_price`         | `Numeric(38, 18)` | No       | —                                        | The resolved quote, **before** slippage.                                                                    |
| `fill_price`        | `Numeric(38, 18)` | No       | —                                        | What the account was actually charged/credited — `raw_price` with slippage applied.                         |
| `fill_time`         | `DateTime(tz)`    | No       | —                                        | When the order was filled.                                                                                  |
| `price_source`      | `String(20)`      | No       | `IN ('ticker', 'trade', 'candle_close')` | Which real data source the quote came from.                                                                 |
| `price_observed_at` | `DateTime(tz)`    | No       | —                                        | When the quote itself was observed (a live event's `event_time`, or the fallback candle's own `open_time`). |
| `is_stale_price`    | `Boolean`         | No       | default `false`                          | `true` if `price_observed_at` was already older than the staleness threshold at fill time.                  |
| `slippage_applied`  | `Numeric(38, 18)` | No       | —                                        | `abs(fill_price - raw_price)` — always a separate, visible column.                                          |
| `fee_applied`       | `Numeric(38, 18)` | No       | —                                        | The modeled fee charged on this fill's notional.                                                            |
| `notional`          | `Numeric(38, 18)` | No       | —                                        | `fill_price × quantity`.                                                                                    |
| `realized_pnl`      | `Numeric(38, 18)` | **Yes**  | —                                        | This order's own contribution to realized PnL. Set only for a **sell**; `NULL` for a buy.                   |

#### `paper_positions` (`PaperPosition`)

| Column                | Type              | Nullable | Constraint                                         | Meaning                                                                        |
| --------------------- | ----------------- | -------- | -------------------------------------------------- | ------------------------------------------------------------------------------ |
| `account_id`          | UUID FK           | No       | `ON DELETE CASCADE`, indexed, unique with `symbol` | Owning account.                                                                |
| `symbol`              | `String(50)`      | No       | indexed, unique with `account_id`                  | One row per (account, symbol) — never duplicated.                              |
| `quantity`            | `Numeric(38, 18)` | No       | `>= 0`, default `0`                                | Currently held quantity. A fully-closed position stays at `0`, is not deleted. |
| `average_entry_price` | `Numeric(38, 18)` | No       | default `0`                                        | VWAP of **fill** prices only across every buy — fees are never blended in.     |

**Materialization, not recomputation:** `PaperPosition` is updated in place by
every buy/sell against that symbol — never recomputed from `PaperOrder`
history on read. This is the same "store the whole answer" precedent
`Prediction`/`EvaluationBenchmarkRun` already established elsewhere on this
platform. "Open positions" (`GET .../positions`) simply filters to
`quantity > 0`.

### 1.4 Price resolution (`app/paper_trading/pricing.py`)

`resolve_current_price(state_manager, candle_repository, market_id, symbol, staleness_threshold)`
tries, in order, and returns as soon as one is available:

1. `MarketStateManager.get_latest_ticker(symbol)` → `price_source="ticker"`, `observed_at` = the ticker's own `event_time`.
2. `MarketStateManager.get_latest_trade(symbol)` → `price_source="trade"`, `observed_at` = the trade's own `event_time`.
3. The latest stored candle at the **finest** timeframe actually stored for
   that symbol (`resolution_duration`, reused from `app.services.candle_ingest`
   — not re-derived) → `price_source="candle_close"`, `observed_at` = that
   candle's own `open_time`.
4. If none of the above exist at all: raises `NoPriceAvailableError` (404,
   `no_price_available`) — there is genuinely nothing to fill against.

This is the identical precedence `MarketStateManager.snapshot()` already uses
for its own metrics view — Paper Trading does not read a second data path.

Every resolved quote's `observed_at` is compared against
`paper_trading_stale_price_threshold_seconds` (default 300s); if older, the
quote (and the resulting fill) is marked `is_stale_price=true`. This check
applies uniformly to all three sources, not just the candle fallback — a
ticker event 6 minutes old is marked stale too.

### 1.5 The fill model (`apply_fill_model`)

A simple fixed-basis-point model — no order-book depth, no liquidity curve,
no venue-specific fee tier (deliberately, per this feature's own scope):

```text
slippage_fraction = slippage_bps / 10_000
fill_price = quote.price × (1 + slippage_fraction)   if side == "buy"
fill_price = quote.price × (1 − slippage_fraction)   if side == "sell"
slippage_applied = abs(fill_price − quote.price)
notional         = fill_price × quantity
fee_applied      = notional × (fee_bps / 10_000)
```

Slippage always moves the price **against** the trader — a buy fills higher
than the quote, a sell fills lower — never in the trader's favor. The fee is
always a cost, on both buys and sells. Worked example at the defaults (5bps
slippage, 10bps fee), a buy of 10 units at a $1000 quote (the exact fixture
`tests/paper_trading/test_pricing.py::TestApplyFillModel` asserts):

- `fill_price` = 1000 × 1.0005 = **$1000.50**
- `slippage_applied` = **$0.50**
- `notional` = 1000.50 × 10 = **$10005.00**
- `fee_applied` = 10005.00 × 0.001 = **$10.005**

### 1.6 The accounting model (`app/services/paper_trading.py`)

**Buy:** rejected with `InsufficientBalanceError` (400,
`insufficient_balance`) if `notional + fee_applied` exceeds the account's
current `balance` — there is no margin, so a buy is either fully affordable
or rejected outright, never partially filled. Otherwise:

- `balance -= (notional + fee_applied)`
- `realized_pnl -= fee_applied` (a buy's own fee is an immediate, certain
  cost — it does not otherwise realize any gain or loss; converting cash
  into a position at cost is not a gain or a loss until sold)
- The position's `average_entry_price` is re-blended as the quantity-weighted
  average of fill prices:
  `new_average = (old_qty × old_average + fill_qty × fill_price) / new_qty`

**Sell:** rejected with `InsufficientPositionError` (400,
`insufficient_position`) if the requested quantity exceeds the currently held
quantity — long-only, so a sell can never exceed the held quantity (no
shorting). Otherwise:

- `realized_pnl_this_order = (fill_price − average_entry_price_before_this_sell) × quantity − fee_applied`
- Account `balance += (notional − fee_applied)`; account `realized_pnl +=
realized_pnl_this_order`
- Position `quantity -= sold_quantity`; `average_entry_price` is **never**
  touched by a sell (only a buy re-blends it)

**Invariant:** once every position an account has ever held is fully closed
(`quantity == 0` everywhere), `balance == starting_balance + realized_pnl`
exactly — every dollar was either spent-then-recovered through a sell, or
never spent at all. This is hand-verified in
`tests/paper_trading/test_service.py`'s `TestHandComputedPnl`.

**Unrealized PnL** (`(current_price − average_entry_price) × quantity`) is
never stored — it's computed fresh on every read of `GET .../positions` or
`GET .../summary`, marked to the same price-lookup path a fill would use, but
with **no slippage or fee applied** — a mark-to-market valuation, not a
hypothetical exit fill.

### 1.7 API endpoints

All mounted under both `/api/v1/*` and unversioned `/*`, tag `paper-trading`.

| Method | Path                                                  | Purpose                                                                | Success status |
| ------ | ----------------------------------------------------- | ---------------------------------------------------------------------- | -------------- |
| POST   | `/paper-trading/accounts`                             | Open a new virtual trading account                                     | 201            |
| GET    | `/paper-trading/accounts`                             | List every account, most recently created first                        | 200            |
| GET    | `/paper-trading/accounts/{account_id}`                | Get one account                                                        | 200            |
| POST   | `/paper-trading/accounts/{account_id}/orders`         | Place and fill one market order                                        | 201            |
| GET    | `/paper-trading/accounts/{account_id}/orders`         | This account's own order history, paginated + sortable                 | 200            |
| GET    | `/paper-trading/accounts/{account_id}/positions`      | This account's currently-open positions                                | 200            |
| GET    | `/paper-trading/accounts/{account_id}/summary`        | Balance, realized PnL, live unrealized PnL, total equity               | 200            |
| GET    | `/paper-trading/accounts/{account_id}/risk`           | Current exposure %/drawdown %, distance to each limit, halted status   | 200            |
| POST   | `/paper-trading/accounts/{account_id}/resume-trading` | Clear a drawdown halt, resetting `peak_balance` to the current balance | 200            |

#### `POST /paper-trading/accounts` — request

```jsonc
{
  "name": "My Account", // optional, max 200 chars, null if omitted
  "starting_balance": "100000", // required, > 0, decimal string
  "max_position_size_pct": "10", // optional, > 0, <= 100 — falls back to the platform default (10)
  "max_exposure_pct": "50", // optional, > 0, <= 100 — falls back to the platform default (50)
  "max_drawdown_pct": "20", // optional, > 0, <= 100 — falls back to the platform default (20)
}
```

#### Account response shape (`PaperAccountResponse`) — every field

| Field                   | Type           | Notes                                                             |
| ----------------------- | -------------- | ----------------------------------------------------------------- |
| `id`                    | string (UUID)  | —                                                                 |
| `name`                  | string \| null | —                                                                 |
| `starting_balance`      | decimal string | Fixed at creation.                                                |
| `balance`               | decimal string | Current cash.                                                     |
| `realized_pnl`          | decimal string | Cumulative.                                                       |
| `max_position_size_pct` | decimal string | Default `10`.                                                     |
| `max_exposure_pct`      | decimal string | Default `50`.                                                     |
| `max_drawdown_pct`      | decimal string | Default `20`.                                                     |
| `peak_balance`          | decimal string | Highest balance ever reached; reset to current balance on resume. |
| `trading_halted`        | boolean        | `true` once a drawdown breach halts the account.                  |
| `created_at`            | ISO-8601 UTC   | e.g. `2026-09-04T10:00:00Z`.                                      |

`GET .../accounts` wraps a page of these in
`{ accounts: [...], total, limit, offset }`. `POST .../resume-trading`
(no request body) also returns this same shape.

#### Risk summary response shape (`RiskSummaryResponse`, `GET .../risk`) — every field

| Field                   | Type           | Notes                                                                           |
| ----------------------- | -------------- | ------------------------------------------------------------------------------- |
| `account_id`            | string (UUID)  | —                                                                               |
| `balance`               | decimal string | Current cash.                                                                   |
| `peak_balance`          | decimal string | —                                                                               |
| `current_exposure_pct`  | decimal string | Total open-position value (current prices) as a % of current balance.           |
| `max_exposure_pct`      | decimal string | —                                                                               |
| `exposure_headroom_pct` | decimal string | `max_exposure_pct - current_exposure_pct`.                                      |
| `current_drawdown_pct`  | decimal string | How far current balance has fallen below `peak_balance`, as a %.                |
| `max_drawdown_pct`      | decimal string | —                                                                               |
| `drawdown_headroom_pct` | decimal string | `max_drawdown_pct - current_drawdown_pct`.                                      |
| `max_position_size_pct` | decimal string | Threshold only — checked per order, per symbol, not as one account-wide figure. |
| `trading_halted`        | boolean        | —                                                                               |

#### `POST /paper-trading/accounts/{account_id}/orders` — request (`PaperOrderRequest`)

```jsonc
{
  "symbol": "ETHUSD", // required
  "side": "buy", // required, "buy" | "sell"
  "quantity": "10", // required, > 0, decimal string, base-asset units
}
```

#### Order response shape (`PaperOrderResponse`) — every field

| Field               | Type                                    | Notes                                               |
| ------------------- | --------------------------------------- | --------------------------------------------------- |
| `id`                | string (UUID)                           | —                                                   |
| `account_id`        | string (UUID)                           | —                                                   |
| `symbol`            | string                                  | —                                                   |
| `side`              | `"buy" \| "sell"`                       | —                                                   |
| `quantity`          | decimal string                          | —                                                   |
| `raw_price`         | decimal string                          | The resolved quote, before slippage.                |
| `fill_price`        | decimal string                          | What was actually charged/credited.                 |
| `fill_time`         | ISO-8601 UTC                            | —                                                   |
| `price_source`      | `"ticker" \| "trade" \| "candle_close"` | Which real data this fill priced from.              |
| `price_observed_at` | ISO-8601 UTC                            | When the quote itself was observed.                 |
| `is_stale_price`    | boolean                                 | `true` if the quote was already stale at fill time. |
| `slippage_applied`  | decimal string                          | `abs(fill_price − raw_price)`.                      |
| `fee_applied`       | decimal string                          | —                                                   |
| `notional`          | decimal string                          | `fill_price × quantity`.                            |
| `realized_pnl`      | decimal string \| null                  | Set only for a sell; `null` for a buy.              |
| `created_at`        | ISO-8601 UTC                            | —                                                   |

`GET .../orders` wraps a page of these in
`{ orders: [...], total, limit, offset }`, with query params:

| Query param | Default      | Allowed values                              |
| ----------- | ------------ | ------------------------------------------- |
| `sort`      | `created_at` | `symbol`, `side`, `fill_time`, `created_at` |
| `dir`       | `desc`       | `asc`, `desc`                               |
| `limit`     | `20`         | `1`–`100`                                   |
| `offset`    | `0`          | `>= 0`                                      |

An unsupported `sort`/`dir` raises `InvalidPaperOrderSortError` (400,
`invalid_paper_order_sort`).

#### Position response shape (`PaperPositionDTO`) — every field

| Field                 | Type                                    | Notes                                                                |
| --------------------- | --------------------------------------- | -------------------------------------------------------------------- |
| `symbol`              | string                                  | —                                                                    |
| `quantity`            | decimal string                          | Currently held.                                                      |
| `average_entry_price` | decimal string                          | VWAP of fill prices.                                                 |
| `current_price`       | decimal string                          | A fresh price-lookup at read time (same precedence as § 1.4).        |
| `price_source`        | `"ticker" \| "trade" \| "candle_close"` | Source of `current_price`.                                           |
| `unrealized_pnl`      | decimal string                          | `(current_price − average_entry_price) × quantity`. No slippage/fee. |

`GET .../positions` returns `{ positions: [...] }` — no pagination (an
account's open-position count is always small).

#### Summary response shape (`PortfolioSummaryResponse`) — every field

| Field                 | Type           | Notes                                                             |
| --------------------- | -------------- | ----------------------------------------------------------------- |
| `account_id`          | string (UUID)  | —                                                                 |
| `balance`             | decimal string | Current cash.                                                     |
| `realized_pnl`        | decimal string | Cumulative.                                                       |
| `unrealized_pnl`      | decimal string | Summed across every currently-open position.                      |
| `total_equity`        | decimal string | `balance` + the live mark-to-market value of every open position. |
| `open_position_count` | integer        | —                                                                 |

### 1.8 Error codes

| HTTP | `code`                       | Raised when                                                                                                         |
| ---- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 400  | `insufficient_balance`       | A buy's `notional + fee` exceeds the account's current cash balance.                                                |
| 400  | `insufficient_position`      | A sell's quantity exceeds what the account currently holds.                                                         |
| 400  | `trading_halted`             | Any order attempted while `trading_halted` is `true`.                                                               |
| 400  | `max_position_size_exceeded` | This order's resulting position value exceeds `max_position_size_pct`.                                              |
| 400  | `max_exposure_exceeded`      | Total exposure after this order exceeds `max_exposure_pct`.                                                         |
| 400  | `invalid_paper_order_sort`   | An unsupported `sort`/`dir` on `GET .../orders`.                                                                    |
| 404  | `paper_account_not_found`    | Unknown `account_id`.                                                                                               |
| 404  | `market_not_found`           | Unknown market `symbol` (reused from `MarketNotFoundError`).                                                        |
| 404  | `no_price_available`         | No live ticker/trade and no candle ever stored for the symbol.                                                      |
| 409  | `account_update_conflict`    | The concurrency guard's bounded retries were all lost (see § 1.9) — practically unreachable by a real two-way race. |

Every error is a structured `{code, detail}` JSON body via `AppError`
subclasses, matching every other domain error on this platform. Every
risk-limit rejection's `detail` names the specific limit and the actual
numbers involved (e.g. _"This order would bring the 'ETHUSD' position to
a value of 15000.00 — 15% of the current balance of 100000.00 —
exceeding the 10% max position size limit for this account"_) — never a
generic message.

### 1.9 Pre-trade risk limits

Three account-level percentage limits, extended onto `paper_accounts`
(migration `c1e00878df40`), plus the running state that enforces them:

| Column                  | Default | Meaning                                                                                                                    |
| ----------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `max_position_size_pct` | `10`    | A single order's resulting position value may never exceed this % of current balance.                                      |
| `max_exposure_pct`      | `50`    | Total open-position value (every symbol, current prices) may never exceed this % of current balance.                       |
| `max_drawdown_pct`      | `20`    | If balance falls below `peak_balance * (1 - this/100)`, `trading_halted` is set.                                           |
| `peak_balance`          | —       | The highest balance this account has ever reached — never decreases (except being reset by an explicit resume, see below). |
| `trading_halted`        | `false` | Set once balance breaches the drawdown limit; cleared only by an explicit resume.                                          |

Settable per account at creation (`PaperAccountCreateRequest`'s optional
`max_position_size_pct`/`max_exposure_pct`/`max_drawdown_pct` fields);
falls back to this platform's configured defaults
(`paper_trading_default_max_position_size_pct`/`_max_exposure_pct`/
`_max_drawdown_pct`, `app/core/config.py`) when omitted.

**Check order in `PaperTradingService.place_order`, every order:**

1. **Halted?** Reject (`trading_halted`) before anything else.
2. **Position sizing** — this order's _resulting_ quantity in its own
   symbol, valued at the _current_ resolved quote (never the price a
   position was originally opened at), against `max_position_size_pct`
   of _current_ balance.
3. **Exposure** — every _other_ open position's current value (the same
   live-price-with-fallback lookup `GET .../positions` already uses) plus
   this order's own resulting value, against `max_exposure_pct` of
   current balance.

**After the trade completes** (never before, never blocking the trade
that causes it): `peak_balance = max(peak_balance, new_balance)`; if
`new_balance < peak_balance * (1 - max_drawdown_pct/100)`,
`trading_halted = true`. This can only flip `false → true` here — a
halted account is rejected at step 1 before ever reaching this point
again.

**No self-healing.** Balance moving back above the threshold on its own
never clears the flag — only `POST .../resume-trading` does, and that
call _also_ resets `peak_balance` to the account's current balance
(without the reset, an account resumed while still deep in drawdown
against its old peak would re-halt after its very next order, regardless
of that order's own direction).

**Concurrency guard** — the same core primitive
`TrainingJobRepository.try_transition_to_running` uses for the
training-job duplicate-run race (a single conditional `UPDATE`, its
matched-row-count telling the caller whether its precondition still
held), adapted into a bounded retry-and-recompute loop because this
feature's precondition (current balance, current prices, every other
open position) can't be pinned to one fixed column the way a training
job's `'pending'` status can:
`PaperAccountRepository.try_apply_trade_effects` runs
`UPDATE ... WHERE balance = :expected AND trading_halted = :expected`.
Two concurrent orders against the same account can never both still
match an unmodified row — the loser's `UPDATE` matches zero rows, and
`place_order` re-reads the account and every open position and retries
(bounded at `paper_trading_max_order_attempts`, default 5) rather than
proceeding on stale numbers. Verified empirically with two real
concurrent requests via `asyncio.gather` — see § 3/§ 4 below.

---

## 2. Frontend

### 2.1 Route and module layout

```text
apps/dashboard/src/app/(dashboard)/paper-trading/page.tsx   Route entry, renders PaperTradingPage

apps/dashboard/src/features/paper-trading/
├── paper-trading-page.tsx                 Composition root
├── paper-trading-page.test.tsx
├── components/
│   ├── account-summary-card.tsx
│   ├── create-account-dialog.tsx
│   ├── live-data-chip.tsx
│   ├── order-form.tsx
│   ├── order-history-table.tsx
│   ├── order-history-table.test.tsx
│   ├── positions-table.tsx
│   └── positions-table.test.tsx
├── hooks/
│   └── use-paper-trading-data.ts          TanStack Query hooks
├── lib/
│   ├── format-pnl.ts                       formatSignedCurrency()
│   └── format-pnl.test.ts
└── store/
    └── use-paper-trading-account-store.ts  Zustand + localStorage, current account id
```

A new **top-level** page (`/paper-trading`, alongside `/trades` and
`/replay`) — not under `/ml/`, since this feature trades against real prices
directly and has nothing to do with a trained model or a prediction. Sidebar
entry: "Paper Trading" (`AccountBalanceWalletIcon`), placed after "Replay".

### 2.2 Complete page layout

Top to bottom, as rendered by `PaperTradingPage`:

1. **Section: "Account"** (subtitle: "A virtual trading account — no real
   money is ever involved"), with a `LiveDataChip` in the section's action
   slot (top-right).
   - An account-switcher `Autocomplete` (only rendered once at least one
     account exists).
   - Either an `EmptyStateNotice` ("No paper trading account yet — Open one
     to start placing simulated market orders against real prices") **or**
     an `AccountSummaryCard`, depending on whether an account is selected.
   - An "Open Account" / "Open Another Account" button.
   - An error `Alert` if account creation just failed.
2. **Section: "Place an Order"** (subtitle: "Market orders only — fills
   immediately at the current real price, with a modeled slippage and fee")
   — contains `OrderForm`, and an error `Alert` if the last order attempt
   failed.
3. **Section: "Positions"** (subtitle: "Every symbol this account currently
   holds") — contains `PositionsTable`.
4. **Section: "Order History"** (subtitle: "Every filled order — fill price,
   source, and the slippage/fee actually applied") — contains
   `OrderHistoryTable`.
5. `CreateAccountDialog`, rendered outside the section flow, opened by the
   "Open Account" button.

Source: `apps/dashboard/src/features/paper-trading/paper-trading-page.tsx:84-186`.

### 2.3 Every field — Create Account Dialog

Component: `CreateAccountDialog` — `components/create-account-dialog.tsx`.

| Field                                                               | Component type                                                           | Required? | Default value | Validation                                                            |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------ | --------- | ------------- | --------------------------------------------------------------------- |
| **Account name**                                                    | MUI `TextField` (`aria-label="Account name"`)                            | No        | `''` (empty)  | None — trimmed to `null` on submit if left blank.                     |
| **Starting balance**                                                | MUI `TextField` (`aria-label="Starting balance"`, `inputMode="decimal"`) | Yes       | `'100000'`    | Submit disabled unless non-empty, finite, and `> 0`.                  |
| **Cancel** button                                                   | MUI `Button`                                                             | —         | —             | Disabled while submitting.                                            |
| **Create Account** button (label becomes "Creating…" while pending) | MUI `Button variant="contained"`                                         | —         | —             | Disabled unless starting balance is valid and not already submitting. |

On submit, calls `POST /paper-trading/accounts` with
`{ name: trimmed-name-or-undefined, starting_balance: <raw string> }`; on
success, the new account becomes the selected account (persisted to
`localStorage`) and the dialog closes.

### 2.4 Every field — Order Form

Component: `OrderForm` — `components/order-form.tsx`.

| Field                                                                                | Component type                                                                                                                | Required? | Default | Allowed values                                 | Validation                                                                                                                                                    |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | --------- | ------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Market**                                                                           | `MarketSelector` (Autocomplete over the same generic, data-driven market picker the chart module uses, `aria-label="Market"`) | Yes       | `null`  | Any `Market.symbol` from `GET /api/v1/markets` | Submit disabled until non-empty.                                                                                                                              |
| **Side** (Buy / Sell)                                                                | MUI `ToggleButtonGroup`, exclusive (`aria-label="Order side"`)                                                                | —         | `'buy'` | `buy`, `sell`                                  | Always has a value (exclusive toggle).                                                                                                                        |
| **Quantity**                                                                         | MUI `TextField` (`aria-label="Quantity"`, `inputMode="decimal"`)                                                              | Yes       | `''`    | Any positive number (base-asset units)         | Submit disabled unless non-empty, finite, and `> 0`.                                                                                                          |
| **Buy `{symbol}` / Sell `{symbol}`** button (label becomes "Placing…" while pending) | MUI `Button variant="contained"`                                                                                              | —         | —       | —                                              | Disabled unless: an account is open, a market is selected, quantity is valid, and not already submitting. Opens a `ConfirmActionDialog`, not a direct submit. |

Each field is paired with an `InfoTooltip`. Submitting the "Buy"/"Sell"
button does **not** place the order directly — it opens a
`ConfirmActionDialog` (title: `"{Buy|Sell} {quantity} {symbol}?"`,
description: "Fills immediately at the current market price, with a modeled
slippage and fee applied — this cannot be undone.", confirm color `primary`
for buy / `error` for sell) so a real (simulated) trade is never a single
accidental click. Confirming calls `POST .../orders` with
`{ symbol, side, quantity }` (quantity sent as the raw string, not
renormalized). If no account is open, an inline `Alert` reads "Open a paper
trading account above before placing an order," and the whole form is
disabled via `hasAccount`.

### 2.5 Every field — Account Summary Card

Component: `AccountSummaryCard` — `components/account-summary-card.tsx`. Data
source: `GET .../summary` (`usePaperPortfolioSummary`, polled every 10s).

| Displayed metric                    | Source field             | Format                                                                                            | Color                                                |
| ----------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Account name (caption, only if set) | `account.name`           | Plain text                                                                                        | —                                                    |
| **Cash Balance**                    | `summary.balance`        | `$X.XX`                                                                                           | Neutral (`text.primary`)                             |
| **Realized PnL**                    | `summary.realized_pnl`   | Signed currency (`formatSignedCurrency` — sign _before_ the `$`, e.g. `-$10.01`, never `$-10.01`) | Green if `> 0`, red if `< 0`, neutral if exactly `0` |
| **Unrealized PnL**                  | `summary.unrealized_pnl` | Same signed-currency format                                                                       | Same green/red/neutral rule                          |
| **Total Equity**                    | `summary.total_equity`   | `$X.XX`                                                                                           | Neutral                                              |

While loading (or no summary yet), renders 4 `Skeleton` placeholders instead
of the metrics.

### 2.6 Every column — Positions Table

Component: `PositionsTable` — `components/positions-table.tsx`, `aria-label="Open positions table"`. Data source: `GET .../positions` (`usePaperPositions`, polled every 10s).

| Column         | Source field          | Format                                            | Notes                                                              |
| -------------- | --------------------- | ------------------------------------------------- | ------------------------------------------------------------------ |
| Symbol         | `symbol`              | Plain text                                        | —                                                                  |
| Quantity       | `quantity`            | Bare number                                       | Right-aligned.                                                     |
| Avg Entry      | `average_entry_price` | `$X.XX`                                           | Right-aligned.                                                     |
| Current Price  | `current_price`       | `$X.XX`                                           | Right-aligned. The same live mark this row's PnL is computed from. |
| Source         | `price_source`        | Outlined `Chip` (`ticker`/`trade`/`candle_close`) | —                                                                  |
| Unrealized PnL | `unrealized_pnl`      | Signed currency                                   | Green/red/neutral, same rule as § 2.5.                             |

Empty state (no open positions): a centered row reading "No open positions —
place a buy order above to open one." Loading state (first load only): 2
skeleton rows.

### 2.7 Every column — Order History Table

Component: `OrderHistoryTable` — `components/order-history-table.tsx`,
`aria-label="Order history table"`. Data source: `GET .../orders`
(`usePaperOrders`, page size 10, **not** auto-polled — refreshes only on
mount/page-change/after a new order is placed).

| Column         | Source field(s)                                       | Format                                                                                                                                                                                                                  | Notes                                                                                        |
| -------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Fill Time      | `fill_time`                                           | `Date.toLocaleString()`                                                                                                                                                                                                 | —                                                                                            |
| Symbol         | `symbol`                                              | Plain text                                                                                                                                                                                                              | —                                                                                            |
| Side           | `side`                                                | `Chip` — green ("BUY") or red ("SELL")                                                                                                                                                                                  | Uppercased.                                                                                  |
| Quantity       | `quantity`                                            | Bare number                                                                                                                                                                                                             | Right-aligned.                                                                               |
| Fill Price     | `fill_price`                                          | `$X.XXXX` (4 decimals)                                                                                                                                                                                                  | Right-aligned.                                                                               |
| Source         | `price_source`, `is_stale_price`, `price_observed_at` | Outlined `Chip` (`ticker`/`trade`/`candle_close`); if stale, a warning icon + `warning` color and a `Tooltip` reading _"Priced from a {source} quote observed {time} — older than this platform's staleness threshold"_ | The one place a stale fallback fill is visibly flagged, never silently presented as current. |
| Slippage / Fee | `slippage_applied`, `fee_applied`                     | `$X.XXXX / $X.XXXX`                                                                                                                                                                                                     | Both always shown together, right-aligned — never hidden behind a drill-down.                |
| Realized PnL   | `realized_pnl`                                        | Signed currency, or an em dash (`—`) when `null` (every buy)                                                                                                                                                            | Green/red/neutral when present.                                                              |

Pagination: MUI `TablePagination`, 10 rows/page, no rows-per-page selector
(`rowsPerPageOptions={[]}`). Empty state: "No orders yet — place one above,
and it will appear here." Loading state (first load only): 3 skeleton rows.

### 2.8 Live Data Chip

Component: `LiveDataChip` — `components/live-data-chip.tsx`. Reads
`useSystemStatus()` (the same `/system/status` poll `live-status.tsx`/the
Health page already use — no second data path). Renders:

- **"Live market data"** (green, filled dot) when `delta_ws_connected` is
  `true`.
- **"Fills use stored candles"** (default gray, gray dot) otherwise.

This is a page-level hint only — the accurate, per-fill signal is the Order
History table's Source column (§ 2.7). This chip deliberately substitutes for
the task's originally-named `ConnectionStatus` component, which is tied to
`useMarketStream` (a live WebSocket hook this page has no other reason to
run) — see `ARCHITECTURE.md` § "Paper Trading" for the full rationale.

### 2.9 Every field — Risk Summary Panel

Component: `RiskSummaryPanel` — `components/risk-summary-panel.tsx`. Data
source: `GET .../risk` (`usePaperTradingRisk`, polled every 10s).

| Element                                     | Component type                                                                        | Behavior                                                                                                                                            |
| ------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Trading active" chip                       | MUI `Chip` (green), shown only when `trading_halted` is `false`                       | —                                                                                                                                                   |
| Halted `Alert`                              | MUI `Alert severity="error" role="alert"`, shown only when `trading_halted` is `true` | Names the drawdown % and peak balance; carries the "Resume Trading" action inline.                                                                  |
| Exposure row                                | Label + `{current}% / {max}% limit` text + `LinearProgress`                           | Bar colored `error` once `current_exposure_pct > max_exposure_pct`, `warning` past 80% of the limit, `primary` otherwise.                           |
| Drawdown row                                | Same shape as Exposure                                                                | Same coloring rule, against `current_drawdown_pct`/`max_drawdown_pct`.                                                                              |
| "Max position size" caption                 | MUI `Typography variant="caption"`                                                    | States `max_position_size_pct` as text only — no "current" figure, since this limit is checked per order/per symbol, not as one account-wide value. |
| "Resume Trading" button (only while halted) | MUI `Button` inside the `Alert`'s action slot                                         | Opens a `ConfirmActionDialog` (title "Resume trading?"); confirming calls `useResumeTrading`'s mutation.                                            |
| Resume error `Alert`                        | MUI `Alert severity="error" role="alert"`, shown only if the resume mutation failed   | The backend's own error message.                                                                                                                    |
| Loading state                               | 2 `Skeleton` placeholders (a text line + a bar, twice)                                | Shown while `isLoading` and no data yet.                                                                                                            |

### 2.10 State management

- **Current account id** — `usePaperTradingAccountStore` (Zustand +
  `localStorage` persist, key `paper-trading-current-account`). Durable
  across page reloads/browser restarts, the same exception
  `use-favorite-features-store.ts` established, since there is no
  authentication on this platform to key a real "my account" off of. `GET
.../accounts` (the account-switcher `Autocomplete`) is the recovery path if
  this is ever cleared.
- **Server state** — TanStack Query, via `hooks/use-paper-trading-data.ts`:

| Hook                           | Query key                                                           | Polling                                |
| ------------------------------ | ------------------------------------------------------------------- | -------------------------------------- |
| `usePaperAccounts(params)`     | `['paper-trading','accounts','list',params]`                        | None (default `staleTime`/`gcTime`)    |
| `usePaperAccount(id)`          | `['paper-trading','account',id]`                                    | None                                   |
| `usePaperPortfolioSummary(id)` | `[...accountKey,'summary']`                                         | Every 10s while an account is selected |
| `usePaperPositions(id)`        | `[...accountKey,'positions']`                                       | Every 10s while an account is selected |
| `usePaperOrders(id, params)`   | `[...accountKey,'orders',params]`                                   | None                                   |
| `usePaperTradingRisk(id)`      | `[...accountKey,'risk']`                                            | Every 10s while an account is selected |
| `useCreatePaperAccount()`      | mutation; invalidates the accounts list on success                  | —                                      |
| `usePlacePaperOrder(id)`       | mutation; invalidates every query under `accountKey(id)` on success | —                                      |
| `useResumeTrading(id)`         | mutation; invalidates every query under `accountKey(id)` on success | —                                      |

Positions and the summary poll because their unrealized PnL depends on a live
price that moves on its own, unprompted by any user action — the same
justification `useTrainingJob` uses to poll a still-running job. Placing an
order invalidates (rather than polls) everything, since it's a
user-triggered, one-shot event.

### 2.11 Loading, empty, and error states — summary

| State                                                       | What renders                                                                                                                                                                                                              |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No account selected                                         | `EmptyStateNotice` — "No paper trading account yet"                                                                                                                                                                       |
| Remembered account id no longer exists                      | Same empty state (the page treats a fetch error on the remembered id as "no account", not a permanent error banner)                                                                                                       |
| Summary/positions loading (first load)                      | Skeletons (§ 2.5 / § 2.6)                                                                                                                                                                                                 |
| Risk panel loading (first load)                             | Skeletons (§ 2.9)                                                                                                                                                                                                         |
| Orders loading (first load)                                 | 3 skeleton rows (§ 2.7)                                                                                                                                                                                                   |
| Account creation fails                                      | Red `Alert role="alert"` under the Account section, with the server's own error message                                                                                                                                   |
| Placing an order fails (including any risk-limit rejection) | Red `Alert role="alert"` under the Place an Order section, with the server's own specific `detail` message (e.g. "insufficient balance", or a named-limit message like "...exceeding the 10% max position size limit...") |
| Resuming trading fails                                      | Red `Alert role="alert"` inside the Risk panel, with the server's own error message                                                                                                                                       |
| No open positions                                           | Centered text row in the Positions table                                                                                                                                                                                  |
| No orders yet                                               | Centered text row in the Order History table                                                                                                                                                                              |

---

## 3. Automated tests

```bash
# Backend
cd services/api
uv run pytest tests/paper_trading/ tests/api/test_paper_trading_api.py -v
uv run pytest tests/paper_trading/ tests/api/test_paper_trading_api.py \
  --cov=app.paper_trading --cov=app.services.paper_trading \
  --cov=app.repositories.paper_trading --cov=app.models.paper_trading \
  --cov-report=term-missing
```

Key files:

- `tests/paper_trading/test_pricing.py` — `TestResolveCurrentPrice`
  (ticker→trade→candle-fallback precedence, staleness marking fresh/stale,
  `NoPriceAvailableError`), `TestApplyFillModel` (exact slippage/fee
  arithmetic, isolated single-variable bps changes).
- `tests/paper_trading/test_service.py` — `TestPlaceOrderFillModel`,
  `TestBalanceAndPositionRejection` (over-balance buy, over-quantity sell
  against a real non-zero holding, sell against nothing), `TestHandComputedPnl`
  (the `$100,000 → buy 10@$1000 → mark-to-market@$1100 → sell 10@$1100`
  fixture), `TestAverageCostBasisAcrossMultipleBuys` (two buys at different
  prices blend to a real VWAP, a partial sell realizes correctly against
  that blend, the remaining position keeps the same blended average).
- `tests/paper_trading/test_service.py` (risk limits) —
  `TestPositionSizeLimit` (an order over the limit rejected, one just
  under it succeeds), `TestExposureLimit` (a position bought cheap whose
  market value has since grown far past its entry cost makes an
  unrelated, otherwise-trivial order rejected — proof the check uses
  _current_, not entry, prices), `TestDrawdownHalt` (a trade that drops
  balance past the drawdown limit halts the account _after_ completing;
  a further order is then rejected until resumed), `TestResumeTrading`
  (resume clears the halt _and_ resets `peak_balance`; a valid order then
  succeeds and the account stays un-halted), and
  `TestConcurrentExposureRace` (two real concurrent orders via
  `asyncio.gather` that would jointly breach exposure — exactly one
  succeeds, the other rejected with `MaxExposureExceededError`, stable
  across repeated runs — mirrors
  `tests/training/test_service.py::test_two_genuinely_concurrent_starts_reject_exactly_one`'s
  exact shape).
- `tests/api/test_paper_trading_api.py` — create/list/reopen account,
  a realistic buy fill over HTTP, all error codes (400/404/409), order/
  position/summary population, invalid sort, an account's real default
  risk limits on creation, a position-size rejection over HTTP, and a
  full risk-summary → drawdown-halt → rejected → resume → succeeds
  walkthrough via `GET .../risk` and `POST .../resume-trading`.

```bash
# Frontend
cd apps/dashboard
pnpm test -- --run src/features/paper-trading
```

Key files: `paper-trading-page.test.tsx` (empty state, account creation,
placing an order end-to-end, a surfaced order error, a halted risk panel's
Resume Trading action), `order-history-table.test.tsx`,
`positions-table.test.tsx`, `risk-summary-panel.test.tsx` (active/halted
rendering, the confirm-before-resume flow, a surfaced resume error, the
loading skeleton), `format-pnl.test.ts` (the shared sign-before-dollar-sign
formatter every PnL figure on this page uses).

---

## 4. Manual test scenarios — real values, step by step

Every value below is real — type it verbatim. Scenarios build on each other;
run them in order. Curl commands assume the API is on
`http://localhost:8000` (adjust the port if yours differs) and use
`jq` to extract ids — drop the `| jq ...` and read the raw JSON if you don't
have `jq` installed.

### Scenario A — Open an account and see it in the UI

**Goal:** confirm account creation works end to end, in the browser.

1. Open `/paper-trading`. **What you should see:** an `EmptyStateNotice`
   reading "No paper trading account yet", and an "Open Account" button.
2. Click **Open Account**. A dialog titled "Open a Paper Trading Account"
   appears.
3. Type `Demo Account` in **Account name**, leave **Starting balance** at its
   default `100000`.
4. Click **Create Account**.
5. **What you should see:** the dialog closes, the Account section now shows
   an account-switcher `Autocomplete` with "Demo Account" selected, and an
   `AccountSummaryCard` reading **Cash Balance $100000.00**, **Realized PnL
   $0.00**, **Unrealized PnL $0.00**, **Total Equity $100000.00**.
6. Refresh the page. **What you should see:** the same account is still
   selected — its id was persisted to `localStorage`, not lost on reload.

### Scenario B — Place a real buy order and read every column it produces

**Goal:** see a real fill, with real slippage/fee/PnL numbers, both in the
API response and in the Order History table.

1. In **Place an Order**, set **Market** to a symbol you know has at least
   one stored candle (e.g. `ETHUSD`). Set **Side** to **Buy**. Set
   **Quantity** to `1`.
2. Click **Buy ETHUSD**. A confirmation dialog appears: "Buy 1 ETHUSD?
   Fills immediately at the current market price, with a modeled slippage
   and fee applied — this cannot be undone."
3. Click **Buy** to confirm.
4. **What you should see in Order History:** one new row. Note its **Fill
   Price** — if your dev database's `market_data_live` is `false` (the
   default), the fill is priced from the symbol's latest stored candle
   close, and the **Source** chip reads `candle_close` (outlined, no
   warning icon unless that candle is genuinely more than 300 seconds
   "old" by wall-clock, which for historical data it always will be —
   check whether the chip shows the warning icon and hover it to read the
   staleness tooltip; either state is a **correct**, honest result for
   this environment, not a bug).
5. Confirm the arithmetic yourself: **Fill Price** should be exactly the
   candle's `close` × 1.0005 (5bps slippage); the **Slippage / Fee** column
   should read `$X.XXXX / $Y.YYYY` where `Y = FillPrice × Quantity × 0.001`
   (10bps fee on the fill's own notional). For example, if the candle's
   close was `2510.20`: Fill Price = `2511.4551`, Slippage = `1.2551`, Fee =
   `2.5114551` — these are the exact real numbers this feature produced
   during development against a real ETHUSD candle in this same dev
   database.
6. **What you should see in Positions:** one row for the symbol you bought,
   **Quantity 1**, **Avg Entry** equal to the fill price from step 5,
   **Current Price** a live mark (same value or close to it), **Unrealized
   PnL** near `$0.00` (it will move slightly if the underlying candle/ticker
   price has changed since the fill).
7. **What you should see in the Account Summary Card:** **Cash Balance**
   reduced by exactly `notional + fee_applied` from Scenario A's `$100000.00`.

### Scenario C — Reject an oversized buy (insufficient balance)

**Goal:** see the balance-negative rejection fire for real, not just in a test.

1. With the same account, set **Quantity** to something absurdly large for
   the remaining cash balance — e.g. `1000000`.
2. Click **Buy**, confirm.
3. **What you should see:** a red `Alert` under Place an Order reading the
   server's own message, e.g. _"Order requires 2,511,455,100.00 (notional +
   fee) but the account only has 99,486.29 available — this account has no
   margin, so the order is rejected rather than partially filled or allowed
   to go negative."_ No new row appears in Order History, and the Cash
   Balance is unchanged.

### Scenario D — Reject an oversell (insufficient position)

**Goal:** see the no-shorting rejection fire against a real, non-zero holding.

1. With the position from Scenario B (quantity `1`), switch **Side** to
   **Sell** and set **Quantity** to `5` (more than the `1` actually held).
2. Click **Sell**, confirm.
3. **What you should see:** a red `Alert` reading _"Cannot sell 5 of
   'ETHUSD': this account holds only 1 — this platform is long-only, so a
   sell can never exceed the held quantity (no shorting)."_
4. Now sell exactly `1` — it should succeed, the position should disappear
   from the Positions table entirely (its `quantity` reaches `0`; the query
   filters to `quantity > 0`), and the Order History should show a second
   row with a non-null **Realized PnL** (the first row, the buy, always
   shows `—`).

### Scenario E — Average cost basis across two different buy prices

**Goal:** confirm the position's average entry price is a real VWAP, not
just the most recent fill — the exact property `TestAverageCostBasisAcrossMultipleBuys`
proves with hand-computed numbers.

1. Open a fresh account (or reuse one with no existing position in a market
   whose price is likely to have moved since your last fill).
2. Buy `10` units. Note the fill price (`P1`) from Order History.
3. Wait for the market's underlying candle/ticker price to change (or pick a
   different, actively-updating market), then buy another `10` units of the
   **same** symbol. Note this fill price (`P2`).
4. **What you should see in Positions:** `Quantity = 20`, and `Avg Entry`
   equal to `(10 × P1 + 10 × P2) / 20` — **not** simply `P2`. If `P1 =
1000.50` and `P2 = 1200.60`, `Avg Entry` should read `$1100.55`.
5. Sell `5` units. Realized PnL on that row should equal
   `(SellFillPrice − 1100.55) × 5 − fee`, and the remaining position (`15`
   units) should keep `Avg Entry = $1100.55` unchanged — a sell never moves
   the average.

### Scenario F — The same walkthrough via curl (no UI required)

**Goal:** exercise the raw API directly — useful for verifying the backend
in isolation, or when you can't drive a browser.

```bash
# 1. Open an account with $100,000
ACCOUNT_ID=$(curl -s -X POST http://localhost:8000/api/v1/paper-trading/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name": "curl-test", "starting_balance": "100000"}' | jq -r '.id')
echo "Account: $ACCOUNT_ID"

# 2. Buy 1 ETHUSD
curl -s -X POST "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "ETHUSD", "side": "buy", "quantity": "1"}' | jq

# Expect: fill_price = raw_price * 1.0005, slippage_applied = fill_price - raw_price,
# fee_applied = fill_price * quantity * 0.001, notional = fill_price * quantity,
# realized_pnl = null (a buy never realizes PnL beyond its own fee).

# 3. Read positions — average_entry_price should equal the buy's fill_price
curl -s "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/positions" | jq

# 4. Read the summary — balance should be 100000 minus (notional + fee) from step 2
curl -s "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/summary" | jq

# 5. Try to oversell — expect HTTP 400, code "insufficient_position"
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "ETHUSD", "side": "sell", "quantity": "999"}'

# 6. Sell the real 1 unit — expect HTTP 201, realized_pnl non-null
curl -s -X POST "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "ETHUSD", "side": "sell", "quantity": "1"}' | jq

# 7. Confirm the reconciliation invariant: once the position is fully closed
#    (as it is here, after selling back all of it), balance == starting_balance + realized_pnl
curl -s "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID" | \
  jq '{starting_balance, balance, realized_pnl,
       expected_balance: ((.starting_balance | tonumber) + (.realized_pnl | tonumber))}'
# `balance` and `expected_balance` should be equal.
```

### Scenario G — An unknown symbol / unknown account (404s)

```bash
# Unknown market
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "DOES-NOT-EXIST", "side": "buy", "quantity": "1"}'
# Expect HTTP 404, code "market_not_found"

# Unknown account
curl -s -w '\nHTTP %{http_code}\n' \
  http://localhost:8000/api/v1/paper-trading/accounts/00000000-0000-0000-0000-000000000000
# Expect HTTP 404, code "paper_account_not_found"
```

### Scenario H — Pre-trade risk limits: position size, exposure, and a drawdown halt

**Goal:** see all three risk limits fire for real, and confirm a halt
requires an explicit resume.

1. Open a fresh account with the real platform defaults (10% position
   size, 50% exposure, 20% drawdown) and `starting_balance = 100000`.
2. In **Place an Order**, buy `11` units of a market whose current price
   is around `$1000` (e.g. `ETHUSD`, if its candle close is near that
   level — otherwise pick a quantity that puts the resulting position
   value just over 10% of your balance).
3. **What you should see:** a red `Alert` naming the specific breach,
   e.g. _"This order would bring the 'ETHUSD' position to a value of
   ... exceeding the 10% max position size limit for this account."_ No
   row appears in Order History.
4. Open the **Risk** section. **What you should see:** an exposure bar
   and a drawdown bar, each reading `0.00% / 50.00% limit` and
   `0.00% / 20.00% limit` respectively (nothing has filled yet), and a
   green "Trading active" chip.
5. Buy a smaller, valid quantity (comfortably under 10%) of a real
   market — this succeeds and now shows up in Risk's exposure bar as a
   nonzero percentage.
6. To see a drawdown halt: open a fresh account with a small
   `starting_balance` (e.g. `10000`) and buy enough of a symbol that the
   total cost (notional + fee) exceeds 20% of that balance — e.g. `2`
   units at a ~$1000 quote. The order itself succeeds (the halt is
   evaluated _after_ it, never blocking it), but the Risk section now
   shows a red halted `Alert` and the drawdown bar in the `error` color,
   over its limit.
7. Try placing any further order. **What you should see:** a red `Alert`
   reading _"Trading is halted for this account: balance ... has fallen
   more than 20% below its peak of ... Resume trading explicitly before
   placing another order."_
8. Click **Resume Trading** on the halted `Alert`, confirm in the
   dialog. **What you should see:** the halted `Alert` disappears, replaced
   by the green "Trading active" chip. Place a small, valid order — it
   now succeeds.

### Scenario I — The exposure limit via curl, proving current-price valuation

```bash
ACCOUNT_ID=$(curl -s -X POST http://localhost:8000/api/v1/paper-trading/accounts \
  -H 'Content-Type: application/json' \
  -d '{"starting_balance": "100000", "max_position_size_pct": "100", "max_exposure_pct": "50"}' \
  | jq -r '.id')

# Buy 1 unit cheap (a market trading near, say, $100)
curl -s -X POST "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "<CHEAP_SYMBOL>", "side": "buy", "quantity": "1"}' | jq '.fill_price'

# Check the risk summary — exposure should be small (~0.1% of balance)
curl -s "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/risk" | jq '.current_exposure_pct'

# Wait for (or pick a market already at) a much higher price, then try a
# tiny order in a *different* symbol — expect HTTP 400, max_exposure_exceeded,
# because the held position is now revalued at its *current*, much higher price.
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  "http://localhost:8000/api/v1/paper-trading/accounts/$ACCOUNT_ID/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "<OTHER_SYMBOL>", "side": "buy", "quantity": "0.001"}'
```

---

## 5. Known gaps / out of scope

Deliberately **not** built (each is a separate, later task, not a defect):

- No margin, no leverage, no shorting — a sell can only reduce/close an
  existing long position.
- No limit/stop orders — market orders only, filled immediately and
  completely; there is no pending/partial-fill state anywhere in the schema.
- No stop-loss/take-profit — a separate, later task; the drawdown halt is
  an account-wide circuit breaker, not a per-position exit order.
- No automation and no prediction-driven trading — every order is placed by
  a human clicking the form; nothing on this platform ever calls
  `POST .../orders` on its own.
- No authentication — "which account is mine" is a `localStorage`-remembered
  id with no server-side identity behind it; anyone who can reach the API can
  read or trade any account by id.
- No order cancellation/deletion endpoint — an order, once filled, is
  permanent history.
- The fill model is a flat basis-point slippage/fee, not an order-book depth
  or liquidity-curve model, and does not vary by venue or order size.
- `CandleClosed`-driven real-time repricing does not exist — a position's
  `current_price`/`unrealized_pnl` is only as fresh as the last poll (10s) or
  the last stored candle, matching the rest of this platform's current
  real-time limitations (see `ARCHITECTURE.md` § "Known Limitations").
