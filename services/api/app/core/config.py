"""Application configuration.

Configuration is loaded from environment variables and an optional .env file.
All future services must follow the conventions in configs/README.md.
Database variables follow the catalog in configs/environment.example.md.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "eth-ai-api"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "DB_URL"),
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    candles_default_limit: int = 100
    candles_max_limit: int = 1000

    experiments_default_limit: int = 50
    experiments_max_limit: int = 200

    training_jobs_default_limit: int = 50
    training_jobs_max_limit: int = 200

    ml_dataset_builds_default_limit: int = 20
    ml_dataset_builds_max_limit: int = 100

    #: How many completed training jobs a single benchmark comparison
    #: (`app/services/evaluation.py`) will ever fetch and compare at once —
    #: a benchmark has no page/offset concept of its own, so this is a flat
    #: cap rather than a default/max pair.
    evaluation_benchmark_max_candidates: int = 100

    #: Benchmark History's list pagination — every successful benchmark
    #: comparison is recorded (best-effort), and this bounds how many past
    #: runs `GET /evaluation/history` returns per page.
    evaluation_history_default_limit: int = 20
    evaluation_history_max_limit: int = 100

    #: Prediction History's list pagination — every successful
    #: `POST /predictions/run` is recorded, and this bounds how many past
    #: predictions `GET /predictions` returns per page.
    predictions_default_limit: int = 20
    predictions_max_limit: int = 100

    #: Backtest History's list pagination — every `POST /backtests/run` call
    #: is recorded, and this bounds how many past runs `GET /backtests`
    #: returns per page.
    backtests_default_limit: int = 20
    backtests_max_limit: int = 100

    #: The largest number of steps a single backtest will ever walk in one
    #: run — mirrors `apps/dashboard/src/features/replay/hooks/use-replay-candles.ts`'s
    #: own `MAX_REPLAY_CANDLES` convention (cap from the end, keep the
    #: earliest portion, report the cap honestly) applied to this platform's
    #: other range-capping feature.
    max_backtest_steps: int = 2000

    #: Where fitted baseline model artifacts are serialized to (joblib), relative
    #: to the service's working directory unless given as an absolute path.
    model_artifact_dir: str = "var/model_artifacts"

    delta_base_url: str = "https://api.india.delta.exchange"
    delta_api_key: str = ""
    delta_api_secret: str = ""
    delta_request_timeout: float = 10.0

    delta_ws_url: str = "wss://public-socket.india.delta.exchange"
    delta_ws_private_url: str = "wss://socket.india.delta.exchange"
    delta_ws_reconnect_delay: float = 2.0
    delta_ws_max_retries: int = 0

    market_data_live: bool = False
    delta_market_symbols: str = "BTCUSD,ETHUSD"

    candle_sync_enabled: bool = True
    candle_sync_interval_seconds: int = 300
    candle_sync_timeframes: str = "1m,5m,15m,30m,1h,4h,1d"
    candle_sync_symbols: str = ""
    candle_sync_backfill_days: int = 7

    #: Periodic prediction grading (`app.services.grading_scheduler.PredictionGradingScheduler`)
    #: — mirrors `candle_sync_enabled`/`candle_sync_interval_seconds` exactly, for the
    #: same reason: a lightweight in-process loop, its own enable flag, no queue/broker.
    prediction_grading_enabled: bool = True
    prediction_grading_interval_seconds: int = 300

    #: Paper Trading's fixed-basis-point execution model
    #: (`app/paper_trading/pricing.py` documents it in full) — a market
    #: order's fill price always moves this many basis points *against* the
    #: trader off the resolved quote, and this many basis points of the
    #: fill's own notional are charged as a fee. Never zero by default: an
    #: unrealistically generous simulation is worse than none.
    paper_trading_slippage_bps: int = 5
    paper_trading_fee_bps: int = 10

    #: A market-triggered stop-loss/take-profit close (`StopLossTakeProfitMonitor`)
    #: applies a *wider* slippage allowance than a manually-placed order —
    #: a triggered exit during a fast price move is not a perfect fill
    #: either, and pretending otherwise would understate exactly the risk
    #: a stop-loss exists to manage. Never equal to or narrower than
    #: `paper_trading_slippage_bps` in the default configuration.
    paper_trading_triggered_slippage_bps: int = 25

    #: How old a resolved price quote (a live ticker/trade's own event_time,
    #: or a fallback candle's own open_time) can be before a fill is marked
    #: `is_stale_price=True` rather than presented as current.
    paper_trading_stale_price_threshold_seconds: int = 300

    #: Paper Trading History pagination.
    paper_trading_accounts_default_limit: int = 20
    paper_trading_accounts_max_limit: int = 100
    paper_trading_orders_default_limit: int = 20
    paper_trading_orders_max_limit: int = 100

    #: Pre-trade risk limits, applied to a new account when its own
    #: `PaperAccountCreateRequest` doesn't override them (see
    #: `app/services/paper_trading.py`). Each is a percentage (e.g. `10`
    #: means 10%), never hardcoded past this one place, so a test can
    #: assert the exact configured threshold.
    paper_trading_default_max_position_size_pct: Decimal = Decimal("10")
    paper_trading_default_max_exposure_pct: Decimal = Decimal("50")
    paper_trading_default_max_drawdown_pct: Decimal = Decimal("20")

    #: Bounded retries for the optimistic-concurrency guard around placing
    #: an order (`PaperAccountRepository.try_apply_trade_effects`) — see
    #: that method's own docstring for why a single atomic `UPDATE` isn't
    #: enough here and a bounded retry-and-recompute loop is needed instead.
    paper_trading_max_order_attempts: int = 5

    #: Periodic automated strategy execution
    #: (`app.services.paper_trading_strategy.PaperTradingStrategyScheduler`)
    #: — mirrors `candle_sync_enabled`/`prediction_grading_enabled` exactly:
    #: this flag only gates whether the *loop* runs at all. Each account's
    #: own `strategy_enabled` (default `False`, `PaperAccount`) is the real,
    #: per-account opt-in — a running loop still does nothing for an
    #: account that never enabled it.
    paper_trading_strategy_scheduler_enabled: bool = True
    paper_trading_strategy_interval_seconds: int = 300

    #: Defaults for a new account's own strategy configuration when its
    #: `PaperStrategyConfigUpdateRequest` doesn't override them — the same
    #: "never hardcoded past this one place" convention every other paper
    #: trading default already follows.
    paper_trading_strategy_default_confidence_threshold_pct: Decimal = Decimal("65")
    paper_trading_strategy_default_stop_loss_pct: Decimal = Decimal("5")

    #: Strategy decision log pagination (`GET .../strategy/decisions`).
    paper_trading_strategy_decisions_default_limit: int = 20
    paper_trading_strategy_decisions_max_limit: int = 100

    #: Alternative.me's free, unauthenticated Fear & Greed Index API
    #: (`app/connectors/fear_greed.py`) — no API key, no signing, unlike
    #: Delta. `fear_greed_request_timeout` mirrors `delta_request_timeout`'s
    #: own role for this connector's own HTTP client.
    fear_greed_base_url: str = "https://api.alternative.me"
    fear_greed_request_timeout: float = 10.0

    #: The St. Louis Fed's FRED API (`app/connectors/fred.py`) — the first
    #: connector that actually requires authentication (`requires_auth=True`
    #: on its own `ConnectorMetadata`, unlike Fear & Greed). An empty key
    #: is a valid, deliberate "not configured yet" state (mirrors every
    #: other optional integration credential on this platform): the
    #: connector still registers, still appears in the catalogue, and only
    #: fails at fetch time with `ConnectorAuthenticationError` if actually
    #: called.
    fred_api_key: str = ""
    fred_base_url: str = "https://api.stlouisfed.org"
    fred_request_timeout: float = 10.0

    #: Etherscan's V2 API (`app/connectors/etherscan.py`) — the second
    #: connector requiring authentication. `etherscan_chain_id` defaults to
    #: `1` (Ethereum mainnet); V2 folds every EVM chain Etherscan supports
    #: behind one base URL, distinguished by this one query parameter.
    #: Same "empty key is a valid not-configured-yet state" contract as
    #: `fred_api_key`.
    etherscan_api_key: str = ""
    etherscan_base_url: str = "https://api.etherscan.io/v2/api"
    etherscan_chain_id: int = 1
    etherscan_request_timeout: float = 10.0

    #: DefiLlama's free API (`app/connectors/defillama.py`) — the fourth
    #: connector, and the first requiring no authentication at all
    #: (confirmed live against DefiLlama's own current docs, not assumed
    #: from history): `defillama_chain` names which chain's TVL to track
    #: (`v2/historicalChainTvl/{chain}`), defaulting to this platform's own
    #: `Ethereum`.
    defillama_base_url: str = "https://api.llama.fi"
    defillama_chain: str = "Ethereum"
    defillama_request_timeout: float = 10.0

    #: CoinGecko's free/Demo API (`app/connectors/coingecko.py`) — the
    #: fifth connector. Unlike FRED/Etherscan, `coingecko_api_key` is
    #: genuinely optional, not merely "not configured yet": `/global`
    #: works fully keyless (confirmed live), and a Demo key only upgrades
    #: the rate limit (100 calls/min, documented) from keyless's own
    #: shared, IP-based limiting — never required for the request to
    #: succeed at all.
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str = ""
    coingecko_request_timeout: float = 10.0

    #: Marketaux news (`app/connectors/marketaux.py`) — the sixth
    #: connector, and genuinely different in shape from every one before
    #: it: real articles land in their own `news_articles` table (not
    #: `external_data_points`), with only a *derived* daily aggregate
    #: sentiment ever mirrored there (source `news_sentiment`) — see
    #: `ConnectorMetadata.auto_synced`. `marketaux_api_key` hard-requires a
    #: key, the same "fail fast, no network call" contract as FRED/
    #: Etherscan, confirmed live (a real unauthenticated request returns a
    #: real HTTP 401). `marketaux_symbols` defaults to this platform's own
    #: primary symbol, in Marketaux's own real entity-symbol convention
    #: (confirmed live/via docs to already match this platform's own
    #: `ETHUSD` — no translation needed). `marketaux_articles_per_page`
    #: mirrors the *free* plan's own real, documented cap (3 articles per
    #: request, verified against Marketaux's current pricing page) —
    #: raise this only if a paid plan is actually in use.
    #: `marketaux_max_pages_per_fetch` bounds how many of the free tier's
    #: 100 requests/day a single `fetch()` call may spend paginating,
    #: chosen so four ticks/day (`news_sync_interval_seconds`'s own
    #: default) stays comfortably inside that budget (4 × 10 = 40
    #: requests/day) with real margin left for a manual backfill run.
    marketaux_base_url: str = "https://api.marketaux.com/v1"
    marketaux_api_key: str = ""
    marketaux_symbols: str = "ETHUSD"
    marketaux_request_timeout: float = 10.0
    marketaux_articles_per_page: int = 3
    marketaux_max_pages_per_fetch: int = 10

    #: Periodic news sync (`app.services.news_sync.NewsSyncScheduler`) —
    #: a *separate*, dedicated scheduler from `ExternalDataSyncScheduler`
    #: (which explicitly excludes `auto_synced=False` sources like this
    #: one), since news ingestion's own shape (persist rich articles,
    #: then recompute and mirror a derived daily aggregate) doesn't fit
    #: the generic "fetch one point, persist it" tick at all. The default
    #: interval (6 hours, 4 ticks/day) is chosen directly from the free
    #: tier's own real 100-requests/day budget — see
    #: `marketaux_max_pages_per_fetch`'s own comment for the arithmetic.
    news_sync_enabled: bool = True
    news_sync_interval_seconds: int = 21600
    #: Window seeded for a first-ever sync with nothing stored yet. Wide
    #: in principle (mirrors `external_data_sync_backfill_days`), but the
    #: free tier's own low per-request article cap means a genuinely wide
    #: historical backfill needs an explicit, patient manual run
    #: (`scripts/backfill_marketaux.py`), not a single periodic tick.
    news_sync_backfill_days: int = 3650

    #: Periodic external data sync (`app.services.external_data_sync
    #: .ExternalDataSyncScheduler`) — mirrors `candle_sync_enabled`/
    #: `candle_sync_interval_seconds` exactly: a lightweight in-process
    #: loop, its own enable flag, no queue/broker. Fear & Greed itself
    #: updates once daily, so the default interval is deliberately much
    #: longer than `candle_sync_interval_seconds`'s own 300s — there is
    #: nothing new to fetch more often than that.
    external_data_sync_enabled: bool = True
    external_data_sync_interval_seconds: int = 3600
    #: Comma-separated connector source names to keep synced; every
    #: registered connector when empty (mirrors `candle_sync_symbols`'s
    #: own "empty means resolve a sensible default" convention).
    external_data_sync_sources: str = ""
    #: Window seeded for a source with no stored data points yet — wider
    #: than `candle_sync_backfill_days`'s own default (7d), since this is
    #: a much lower-volume, lower-frequency data source and a full history
    #: is cheap to fetch in one request (see `FearGreedConnector.fetch`).
    external_data_sync_backfill_days: int = 3650


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
