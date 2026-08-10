# System Context Diagram (C4 Model – Level 1)

## Document Information

**Document:** System Context Diagram — C4 Model, Level 1

**Scope:** Highest-level architectural view of the platform

**Status:** Draft

---

## 1. System Boundary

The platform — the AI-Powered Ethereum Market Analysis and Probabilistic Prediction
Platform — is the single system under design at this level of abstraction.

**Inside the system boundary:**

- Market data collection and ingestion
- Historical data storage and management
- Live market data streaming
- Feature engineering and computation
- AI model training and experimentation
- Probabilistic prediction and forecasting
- Backtesting and validation
- Paper trading simulation
- Portfolio analytics
- Risk management and scenario analysis
- Order management (simulated and live)
- Exchange connectivity and execution
- Monitoring, observability, and administration
- User interfaces for all roles

**Outside the system boundary:**

- Human users interacting with the platform through their own devices and browsers
- External data providers and market information sources
- External cryptocurrency exchanges
- Regulatory, legal, and financial institutions

The platform consumes information from external systems, produces analytical outputs
for its users, and executes trading-related operations through external exchanges.
All other systems are outside the boundary and are treated purely as black boxes.

---

## 2. Human Actors

| Actor             | Description                                                                                                                                                                                                            |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Administrator** | Manages platform configuration, user accounts, data retention, system health, and operational security. Interacts with administration, monitoring, and configuration capabilities.                                     |
| **Researcher**    | Conducts quantitative research: accesses data, engineers features, trains and evaluates models, runs backtests, and documents findings. Interacts with research, data, and model management capabilities.              |
| **Trader**        | Uses analytical outputs and probabilistic forecasts to design, validate, and monitor strategies through paper trading and live trading. Interacts with analytics, prediction, risk, and order management capabilities. |
| **Analyst**       | Consumes platform outputs for market analysis, reporting, and decision support. Reviews data, predictions, risk assessments, and published research without modifying platform state.                                  |

All actors interact with the platform exclusively through its user-facing capabilities.
None of the actors interact directly with external systems; all external communication
is mediated by the platform.

---

## 3. External Systems

| External System                       | Purpose                                                                                                                                                                            |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Delta Exchange India**              | Primary source of live and historical market data — including trades, order books, candles, and funding rates — and the execution venue for simulated and live trading operations. |
| **CoinGecko**                         | Provides aggregated market data — including prices, market capitalization, trading volumes, and broader market statistics — used for cross-market context and validation.          |
| **Marketaux**                         | Supplies news and sentiment data used to derive market sentiment features for analysis and prediction.                                                                             |
| **Etherscan**                         | Provides on-chain Ethereum blockchain data — including transactions, blocks, addresses, and network activity — used for on-chain feature engineering.                              |
| **FRED**                              | Supplies macroeconomic and financial time series — including interest rates and monetary aggregates — used to capture macroeconomic context in market analysis.                    |
| **Alternative.me Fear & Greed Index** | Provides a sentiment index quantifying market fear and greed, used as a sentiment signal in feature engineering and analysis.                                                      |
| **DefiLlama**                         | Supplies decentralized finance (DeFi) metrics — including total value locked and protocol data — used for DeFi market context and feature engineering.                             |

These external systems are information sources and execution venues only. The
platform defines the data contracts, retrieval policies, and error handling for
each integration, but their internal workings remain entirely external.

---

## 4. High-Level Data Flow

**Inbound data flow (information entering the platform):**

1. Market data — trades, order books, candles, funding rates — flows from
   **Delta Exchange India** into the platform's data collection layer.
2. Market statistics and aggregated data flow from **CoinGecko**.
3. News and sentiment data flow from **Marketaux**.
4. On-chain blockchain data flows from **Etherscan**.
5. Macroeconomic time series flow from **FRED**.
6. Fear and Greed sentiment index flows from **Alternative.me**.
7. DeFi metrics flow from **DefiLlama**.

This data is ingested, validated, stored, and processed by the platform to produce
features, models, predictions, and analytical outputs.

**Internal data flow (within the system boundary):**

- Raw data is stored and transformed into features.
- Features feed model training and the prediction engine.
- Predictions feed backtesting, paper trading, portfolio analytics, and risk
  management.
- Analytical outputs are made available to all actors through user-facing
  capabilities.

**Outbound data flow (information leaving the platform):**

1. Analytical outputs — predictions, risk assessments, reports, and research
   findings — are delivered to all human actors through the platform interfaces.
2. Trading instructions are sent to **Delta Exchange India** for simulated and
   live order execution.
3. Execution confirmations and account/position data flow back into the platform.

No other external system receives outbound data from the platform.

---

## 5. Mermaid System Context Diagram

```mermaid
C4Context
    title System Context Diagram — AI-Powered Ethereum Market Analysis and Probabilistic Prediction Platform

    Person(admin, "Administrator", "Manages platform configuration, users, and system health")
    Person(researcher, "Researcher", "Conducts quantitative research, model training, and backtesting")
    Person(trader, "Trader", "Uses forecasts to design and validate strategies via paper and live trading")
    Person(analyst, "Analyst", "Consumes market analysis, predictions, and reports for decision support")

    System(platform, "Ethereum Market Analysis and Probabilistic Prediction Platform",
        "Collects market data, engineers features, trains AI models, produces probabilistic forecasts,
        performs backtesting and paper trading, manages portfolios and risk, and executes trades")

    System_Ext(delta, "Delta Exchange India",
        "Market data (trades, order books, candles, funding rates) and trade execution venue")
    System_Ext(coinGecko, "CoinGecko", "Aggregated market statistics and cross-market context")
    System_Ext(marketaux, "Marketaux", "News and sentiment data")
    System_Ext(etherscan, "Etherscan", "On-chain Ethereum blockchain data")
    System_Ext(fred, "FRED", "Macroeconomic time series")
    System_Ext(altme, "Alternative.me Fear & Greed Index", "Market sentiment index")
    System_Ext(defillama, "DefiLlama", "DeFi metrics and total value locked data")

    Rel(admin, platform, "Administers, configures, monitors")
    Rel(researcher, platform, "Accesses data, trains models, runs backtests")
    Rel(trader, platform, "Consumes forecasts, manages strategies and orders")
    Rel(analyst, platform, "Reviews analysis, predictions, and reports")

    Rel(platform, delta, "Consumes market data; sends trading instructions")
    Rel(delta, platform, "Provides market data; confirms executions")
    Rel(platform, coinGecko, "Consumes aggregated market statistics")
    Rel(platform, marketaux, "Consumes news and sentiment data")
    Rel(platform, etherscan, "Consumes on-chain blockchain data")
    Rel(platform, fred, "Consumes macroeconomic time series")
    Rel(platform, altme, "Consumes sentiment index")
    Rel(platform, defillama, "Consumes DeFi metrics")
```

---

## 6. Architecture Notes

### Key Assumptions

1. The platform operates as a single deployable system from an architectural
   perspective; internal decomposition is defined at C4 Level 2 and beyond.
2. All external systems are accessed over network boundaries and are treated as
   unreliable — the platform must handle outages, rate limits, and data
   inconsistencies gracefully.
3. Human actors interact only through platform-provided interfaces; no direct
   actor-to-external-system communication occurs.
4. The platform mediates all trading operations; it never relies on actors to
   communicate with exchanges directly.
5. Data volumes and update frequencies are sufficient to justify continuous data
   collection and streaming capabilities but are not assumed to be unbounded.
6. The platform is research- and decision-support-oriented and does not provide
   financial advice or guarantee trading outcomes.

### Exclusions

1. No database, API, or service-level design is addressed at this level.
2. No technology or implementation choices are made at this level.
3. No deployment topology or infrastructure decisions are made at this level.
4. No security mechanisms are specified beyond the acknowledgment of security
   boundaries.
5. Additional external systems beyond those listed are excluded.

### Future Expansion Points

1. Additional data providers and information sources may be integrated as market
   analysis requirements evolve.
2. Additional exchanges may be added as execution and data venues.
3. New actor roles may be introduced as platform capabilities expand.
4. Additional asset classes and market types may be supported within the same
   system boundary.
5. New analytical capabilities — such as advanced risk models or alternative
   prediction methodologies — may be added without changing the system context.
