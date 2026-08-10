# Domain Model — Bounded Contexts

## Document Information

**Document:** Bounded Contexts — Domain-Driven Design

**Scope:** Logical domain boundaries of the platform

**Status:** Draft

---

## 1. Domain Overview

The platform is decomposed into thirteen bounded contexts, each owning a distinct
slice of the domain. The decomposition follows Domain-Driven Design principles:
high cohesion within each context, loose coupling between contexts, no shared data
ownership, and no duplicated responsibilities.

Each bounded context owns its data model and exposes its capabilities through
explicit interfaces. Contexts never access another context's data directly — all
cross-context data exchange occurs through well-defined contracts (commands, events,
or queries). The boundaries defined here are logical; they map to the container
architecture (C4 Level 2) and will guide physical deployment decisions.

**Context map summary:**

| #    | Bounded Context              | Domain                                              | Core / Supporting / Generic |
| ---- | ---------------------------- | --------------------------------------------------- | --------------------------- |
| BC1  | Identity & Access Management | Users, roles, permissions, sessions                 | Generic                     |
| BC2  | Market Data                  | Data collection, historical storage, live streaming | Core                        |
| BC3  | Feature Engineering          | Features, datasets, versioning                      | Core                        |
| BC4  | AI Research & Training       | Experiments, models, model registry                 | Core                        |
| BC5  | Prediction                   | Probabilistic forecasts                             | Core                        |
| BC6  | Strategy Management          | Strategy definitions and evaluation                 | Core                        |
| BC7  | Backtesting                  | Historical simulation and validation                | Core                        |
| BC8  | Trading Execution            | Order lifecycle, simulated and live trading         | Core                        |
| BC9  | Portfolio Management         | Portfolios, positions, performance                  | Supporting                  |
| BC10 | Risk Management              | Risk metrics, limits, scenarios                     | Core                        |
| BC11 | Analytics & Reporting        | Analysis outputs, reports, dashboards               | Supporting                  |
| BC12 | Notifications                | Alerts and user notifications                       | Generic                     |
| BC13 | Administration & Operations  | Configuration, scheduling, observability            | Supporting                  |

---

## 2. List of Bounded Contexts

### BC1 — Identity & Access Management

- **Purpose:** Establish and govern the identity of every actor and the access they
  have to platform capabilities.
- **Responsibilities:** User registration and account lifecycle; authentication and
  session management; role and permission administration; authorization decisions
  for all platform operations.
- **Data owned:** Users, credentials, roles, permissions, sessions, audit records of
  access events.
- **Data consumed:** Requests for authentication and authorization; user lifecycle
  events from administration workflows.
- **Data produced:** Authentication results, authorization decisions, user and role
  records, access audit events.
- **External dependencies:** None (identity is internal; federation is a future
  expansion).
- **Communicates with:** All contexts that accept user-initiated operations —
  primarily via the platform's service boundary.
- **Why this boundary exists:** Identity is a cross-cutting concern with its own
  lifecycle, security requirements, and audit obligations. Isolating it keeps
  security policy in one place and prevents every context from reinventing access
  control.

### BC2 — Market Data

- **Purpose:** Acquire, normalize, store, and distribute market information from
  external systems.
- **Responsibilities:** Pulling data from external providers; normalizing and
  standardizing records; managing historical data storage and retrieval; providing
  live data streaming; enforcing data quality at ingestion; reconciling execution
  and market state.
- **Data owned:** Raw and normalized market data — trades, order books, candles,
  funding rates, on-chain data, sentiment, macro and DeFi metrics; data source
  configuration and collection state.
- **Data consumed:** External provider feeds and APIs; scheduling instructions.
- **Data produced:** Curated market data; live market event streams; data quality
  reports.
- **External dependencies:** Delta Exchange India, CoinGecko, Marketaux, Etherscan,
  FRED, Alternative.me, DefiLlama.
- **Communicates with:** Feature Engineering (provides raw and curated data),
  Prediction (live signals), Trading Execution (reconciliation data), Backtesting
  (historical data), Administration & Operations (collection state).
- **Why this boundary exists:** External integration complexity — provider
  variability, rate limits, outages, schema differences — is confined here so that
  the rest of the platform consumes a stable, normalized view of the market.

### BC3 — Feature Engineering

- **Purpose:** Transform raw market data into reliable, versioned, reusable features
  for training and inference.
- **Responsibilities:** Computing derived features; maintaining feature definitions;
  versioning feature values and datasets; serving features consistently to training
  and serving pipelines; validating feature quality.
- **Data owned:** Feature definitions, feature values, computed datasets, feature
  lineage metadata.
- **Data consumed:** Curated market data from Market Data; live market events from
  Market Data streaming.
- **Data produced:** Versioned feature values and datasets.
- **External dependencies:** None.
- **Communicates with:** Market Data (consumes), AI Research & Training (provides
  training features), Prediction (provides inference features), Backtesting
  (provides historical features).
- **Why this boundary exists:** Feature computation must be identical for training
  and inference — training/serving skew is one of the most damaging failure modes
  in AI systems. A dedicated context guarantees consistency, versioning, and
  reproducibility.

### BC4 — AI Research & Training

- **Purpose:** Support the complete model development lifecycle with reproducibility
  and transparency.
- **Responsibilities:** Managing experiment configurations; training and evaluating
  models; tracking experiments and results; maintaining the model registry;
  promoting models to serving; documenting research findings.
- **Data owned:** Experiments, training runs, evaluation results, model artifacts,
  model registry entries, research documentation.
- **Data consumed:** Versioned features and datasets; metadata about data provenance.
- **Data produced:** Trained model artifacts; experiment and evaluation records;
  registered, deployable models.
- **External dependencies:** None.
- **Communicates with:** Feature Engineering (consumes), Prediction (deploys models),
  Analytics & Reporting (research outputs), Administration & Operations (training
  schedules).
- **Why this boundary exists:** Research workloads are computationally heavy,
  exploratory, and long-running. Isolating them protects production serving from
  interference and keeps the research lifecycle distinct from production concerns.

### BC5 — Prediction

- **Purpose:** Produce calibrated, probabilistic forecasts from registered models.
- **Responsibilities:** Serving models for batch and real-time inference; applying
  uncertainty quantification; logging predictions with full provenance; managing
  model versions, canary releases, and rollbacks.
- **Data owned:** Prediction records, serving model configurations, prediction
  provenance metadata.
- **Data consumed:** Inference features from Feature Engineering; live signals from
  Market Data; registered models from AI Research & Training.
- **Data produced:** Probabilistic forecasts — distributions, confidence intervals,
  scenario-weighted outcomes.
- **External dependencies:** None.
- **Communicates with:** Feature Engineering, Market Data, AI Research & Training,
  Strategy Management (serves forecasts), Backtesting (evaluates forecasts), Risk
  Management (provides uncertainty inputs), Analytics & Reporting.
- **Why this boundary exists:** Serving is a stable, operational concern with strict
  reliability and latency requirements; keeping it separate from research allows
  models to evolve without destabilizing the serving surface.

### BC6 — Strategy Management

- **Purpose:** Define, manage, and evaluate trading strategies as first-class domain
  artifacts.
- **Responsibilities:** Managing strategy definitions and configuration; translating
  strategies into executable logic; monitoring strategy performance; enforcing
  strategy-level constraints; controlling the lifecycle of strategies through
  paper trading to live trading.
- **Data owned:** Strategy definitions, strategy configuration, strategy lifecycle
  state, strategy performance records.
- **Data consumed:** Forecasts from Prediction; risk metrics from Risk Management;
  portfolio state from Portfolio Management.
- **Data produced:** Strategy signals; execution intents; strategy evaluation
  requests.
- **External dependencies:** None.
- **Communicates with:** Prediction, Risk Management, Portfolio Management,
  Backtesting (evaluates strategies), Trading Execution (submits intents),
  Analytics & Reporting.
- **Why this boundary exists:** Strategy logic is the most rapidly evolving research
  artifact in the platform. Isolating it from execution mechanics and risk controls
  lets strategies evolve without touching safety-critical infrastructure.

### BC7 — Backtesting

- **Purpose:** Validate strategies and models against historical data under
  realistic, auditable conditions.
- **Responsibilities:** Simulating strategy execution on historical data; modeling
  slippage, fees, and data availability; producing performance and validation
  metrics; supporting walk-forward and scenario-based validation; maintaining
  reproducible backtest records.
- **Data owned:** Backtest runs, simulation results, validation metrics, backtest
  configuration.
- **Data consumed:** Historical data from Market Data; features from Feature
  Engineering; forecasts from Prediction; strategy definitions from Strategy
  Management.
- **Data produced:** Backtest results and performance reports.
- **External dependencies:** None.
- **Communicates with:** Market Data, Feature Engineering, Prediction, Strategy
  Management, Analytics & Reporting, Administration & Operations.
- **Why this boundary exists:** Simulation rigor — statistical soundness,
  absence of look-ahead bias, realistic cost modeling — is a distinct discipline
  with its own rules. Centralizing it ensures all performance claims are produced
  under consistent, auditable conditions.

### BC8 — Trading Execution

- **Purpose:** Manage the complete lifecycle of orders for both simulated (paper)
  and live trading.
- **Responsibilities:** Accepting execution intents; validating against risk
  decisions; simulating fills for paper trading; submitting and managing orders on
  exchanges for live trading; reconciling execution state; handling failures and
  retries.
- **Data owned:** Orders, executions, fills, exchange account state, execution
  reconciliation records.
- **Data consumed:** Execution intents from Strategy Management; risk decisions
  from Risk Management; market state from Market Data.
- **Data produced:** Order and execution records; position updates; execution
  events.
- **External dependencies:** Delta Exchange India (execution venue for live trading).
- **Communicates with:** Strategy Management, Risk Management, Portfolio Management
  (position updates), Market Data (reconciliation), Notifications (execution
  alerts).
- **Why this boundary exists:** Execution mechanics — venue protocols, order types,
  failure semantics, reconciliation — must be isolated from strategy and analytics
  so that safety-critical trading operations evolve under strict control.

### BC9 — Portfolio Management

- **Purpose:** Maintain the authoritative view of portfolios, positions, and
  performance.
- **Responsibilities:** Tracking portfolio composition; recording positions and
  balances; computing performance and attribution; managing paper and live
  portfolio state; supporting portfolio analytics.
- **Data owned:** Portfolios, positions, balances, performance records, holdings
  history.
- **Data consumed:** Execution records from Trading Execution; market values from
  Market Data; risk metrics from Risk Management.
- **Data produced:** Portfolio state, performance analytics, position summaries.
- **External dependencies:** None.
- **Communicates with:** Trading Execution, Risk Management, Strategy Management,
  Analytics & Reporting, Prediction (contextual analytics).
- **Why this boundary exists:** A single authoritative portfolio state must exist —
  duplicated or divergent portfolio views across contexts would undermine every
  downstream analytical claim.

### BC10 — Risk Management

- **Purpose:** Quantify risk and enforce risk limits across the platform.
- **Responsibilities:** Computing risk metrics — volatility, drawdown, value at
  risk, tail risk; running scenario and stress analyses; enforcing pre-trade and
  post-trade risk limits; producing risk assessments and reports.
- **Data owned:** Risk models, risk metrics, limit definitions, limit breach
  records, scenario definitions.
- **Data consumed:** Portfolio state, market data, forecasts, execution intents.
- **Data produced:** Risk metrics, limit decisions, scenario assessments, risk
  reports.
- **External dependencies:** None.
- **Communicates with:** Portfolio Management, Strategy Management, Trading
  Execution (pre-trade validation), Prediction, Analytics & Reporting,
  Notifications (risk alerts).
- **Why this boundary exists:** Risk policy must be independent of the actors it
  constrains. If risk logic lived inside strategy or execution contexts, the
  enforcing party would also be the checked party — an unacceptable control
  design.

### BC11 — Analytics & Reporting

- **Purpose:** Produce analysis outputs, reports, and dashboards that translate raw
  domain data into decision-support information.
- **Responsibilities:** Aggregating and interpreting platform data; producing
  analytical reports; composing dashboards and export artifacts; documenting
  research outputs for publication.
- **Data owned:** Report definitions, published reports, dashboard definitions,
  analytical summaries.
- **Data consumed:** Data and outputs from all analytical contexts — predictions,
  backtests, portfolio analytics, risk assessments, research results.
- **Data produced:** Reports, dashboards, exported artifacts, published findings.
- **External dependencies:** None.
- **Communicates with:** All analytics-producing contexts; the presentation layer
  via the platform service boundary.
- **Why this boundary exists:** Reporting and interpretation are consumer concerns
  that should not force analytic contexts to know about presentation formats,
  scheduling, or publication channels.

### BC12 — Notifications

- **Purpose:** Deliver alerts and notifications to users across channels.
- **Responsibilities:** Managing notification preferences; composing and delivering
  notifications; tracking delivery state; routing alert events to appropriate
  channels.
- **Data owned:** Notification preferences, notification records, delivery state.
- **Data consumed:** Alert events from Risk Management, Trading Execution,
  Prediction, Administration & Operations.
- **Data produced:** Delivered notifications.
- **External dependencies:** None (channels are internal in the first iteration).
- **Communicates with:** Risk Management, Trading Execution, Prediction,
  Administration & Operations, presentation layer.
- **Why this boundary exists:** Notification policy — what to notify, how, when,
  and to whom — is a generic concern that should be managed independently of the
  contexts that generate events.

### BC13 — Administration & Operations

- **Purpose:** Operate and govern the platform — configuration, scheduling, and
  observability.
- **Responsibilities:** Managing platform configuration; orchestrating scheduled
  workloads; collecting metrics, logs, and traces; detecting anomalies and
  producing operational alerts; administering data retention and maintenance.
- **Data owned:** Configuration, job definitions, job execution history,
  operational metadata.
- **Data consumed:** Telemetry from all contexts; configuration changes.
- **Data produced:** Operational alerts, scheduled job invocations, configuration
  state, observability data.
- **External dependencies:** None.
- **Communicates with:** Every context (telemetry collection, job orchestration,
  configuration distribution).
- **Why this boundary exists:** Operational concerns are orthogonal to domain
  concerns. Centralizing them prevents each context from implementing its own
  scheduling, logging, and configuration mechanisms.

---

## 3. Responsibilities

### BC1 — Identity & Access Management

- Govern user, role, and permission lifecycles.
- Authenticate actors and authorize operations.
- Maintain access audit records.

### BC2 — Market Data

- Collect and normalize external market data.
- Store and retrieve historical data.
- Stream live market data.
- Enforce ingestion data quality.

### BC3 — Feature Engineering

- Compute derived features from raw data.
- Version features and datasets.
- Serve consistent features for training and inference.

### BC4 — AI Research & Training

- Manage experiment lifecycle.
- Train and evaluate models.
- Maintain the model registry and promote models to serving.

### BC5 — Prediction

- Serve batch and real-time probabilistic forecasts.
- Apply uncertainty quantification.
- Maintain prediction provenance and model versioning.

### BC6 — Strategy Management

- Define and configure strategies.
- Translate strategies into executable logic.
- Manage strategy lifecycle from paper to live.

### BC7 — Backtesting

- Simulate strategies on historical data.
- Model realistic execution conditions.
- Produce auditable validation metrics.

### BC8 — Trading Execution

- Execute simulated and live orders.
- Reconcile execution state.
- Handle execution failures and retries.

### BC9 — Portfolio Management

- Track portfolios, positions, and balances.
- Compute performance and attribution.
- Provide authoritative portfolio state.

### BC10 — Risk Management

- Compute risk metrics.
- Enforce pre-trade and post-trade limits.
- Run scenario and stress analyses.

### BC11 — Analytics & Reporting

- Compose reports and dashboards.
- Publish research outputs.
- Produce decision-support summaries.

### BC12 — Notifications

- Manage notification preferences.
- Deliver alerts across channels.
- Track delivery state.

### BC13 — Administration & Operations

- Manage platform configuration.
- Orchestrate scheduled workloads.
- Collect observability data and produce operational alerts.

---

## 4. Communication Matrix

| From \ To                  | BC1 | BC2 | BC3 | BC4 | BC5 | BC6 | BC7 | BC8 | BC9 | BC10 | BC11 | BC12 | BC13 |
| -------------------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---- | ---- | ---- | ---- |
| BC1 Identity & Access      | —   | •   | •   | •   | •   | •   | •   | •   | •   | •    | •    | •    | •    |
| BC2 Market Data            | —   | —   | →   |     | →   |     | →   | →   |     |      | →    |      | →    |
| BC3 Feature Engineering    |     | —   |     | →   | →   |     | →   |     |     |      |      |      |      |
| BC4 AI Research & Training |     |     | ←   | —   | →   |     |     |     |     |      | →    |      | →    |
| BC5 Prediction             |     | ←   | ←   | ←   | —   | →   | →   |     | →   | →    | →    |      |      |
| BC6 Strategy Management    |     |     |     |     | ←   | —   | →   | →   | ←   | →    | →    |      |      |
| BC7 Backtesting            |     | ←   | ←   |     | ←   | ←   | —   |     |     |      | →    |      | →    |
| BC8 Trading Execution      |     | →   |     |     |     | ←   |     | —   | →   | ←    |      | →    |      |
| BC9 Portfolio Management   |     |     |     |     |     | →   |     | ←   | —   | →    | →    |      |      |
| BC10 Risk Management       |     |     |     |     | ←   | →   |     | →   | ←   | —    | →    | →    |      |
| BC11 Analytics & Reporting |     |     |     |     |     |     |     |     |     |      | —    |      |      |
| BC12 Notifications         |     |     |     |     |     |     |     |     |     |      |      | —    |      |
| BC13 Administration & Ops  |     | →   |     | →   |     |     | →   |     |     |      |      | →    | —    |

**Legend:** `—` same context; `→` producer → consumer; `←` consumer; `•` authorization/identity dependency (BC1 is consulted, not consumed as data).

---

## 5. Mermaid Context Relationship Diagram

```mermaid
C4Context
    title Bounded Contexts — Domain Relationship Diagram

    Boundary(bc1, "BC1 Identity & Access Management", "Users, roles, permissions, sessions")
    Boundary(bc2, "BC2 Market Data", "External ingestion, historical storage, live streaming")
    Boundary(bc3, "BC3 Feature Engineering", "Versioned features and datasets")
    Boundary(bc4, "BC4 AI Research & Training", "Experiments, model registry")
    Boundary(bc5, "BC5 Prediction", "Probabilistic forecasts")
    Boundary(bc6, "BC6 Strategy Management", "Strategy definitions and lifecycle")
    Boundary(bc7, "BC7 Backtesting", "Historical simulation, validation")
    Boundary(bc8, "BC8 Trading Execution", "Order lifecycle, simulated and live")
    Boundary(bc9, "BC9 Portfolio Management", "Portfolios, positions, performance")
    Boundary(bc10, "BC10 Risk Management", "Risk metrics, limits, scenarios")
    Boundary(bc11, "BC11 Analytics & Reporting", "Reports, dashboards, publications")
    Boundary(bc12, "BC12 Notifications", "Alerts, delivery channels")
    Boundary(bc13, "BC13 Administration & Operations", "Configuration, scheduling, observability")

    Rel(bc2, bc3, "Curated data and live events")
    Rel(bc3, bc4, "Training features and datasets")
    Rel(bc3, bc5, "Inference features")
    Rel(bc4, bc5, "Registered models")
    Rel(bc5, bc6, "Probabilistic forecasts")
    Rel(bc5, bc7, "Forecast evaluation inputs")
    Rel(bc6, bc7, "Strategy definitions for validation")
    Rel(bc6, bc8, "Execution intents")
    Rel(bc6, bc10, "Pre-trade checks")
    Rel(bc7, bc11, "Validation results")
    Rel(bc8, bc9, "Execution and position updates")
    Rel(bc8, bc2, "Reconciliation data")
    Rel(bc9, bc10, "Portfolio state for risk assessment")
    Rel(bc10, bc8, "Risk decisions")
    Rel(bc10, bc12, "Risk alerts")
    Rel(bc10, bc11, "Risk reports")
    Rel(bc9, bc11, "Performance analytics")
    Rel(bc11, bc1, "Authorized presentation access")
    Rel(bc13, bc2, "Schedules collection")
    Rel(bc13, bc4, "Schedules training")
    Rel(bc13, bc7, "Schedules backtests")
    Rel(bc13, bc12, "Operational alerts")
    Rel(bc13, bc5, "Monitoring")
    Rel(bc1, bc6, "Authorizes strategies")
    Rel(bc1, bc8, "Authorizes execution")
```

---

## 6. Suggested Repository Mapping

The repository layout mirrors the bounded contexts so that each context is a
self-contained unit with explicit ownership.

```text
platform/
├── apps/                        # Deployable applications (composition roots)
├── services/                    # One module per bounded context
│   ├── identity/                # BC1 — Identity & Access Management
│   ├── market-data/             # BC2 — Market Data
│   ├── features/                # BC3 — Feature Engineering
│   ├── research/                # BC4 — AI Research & Training
│   ├── prediction/              # BC5 — Prediction
│   ├── strategy/                # BC6 — Strategy Management
│   ├── backtesting/             # BC7 — Backtesting
│   ├── execution/               # BC8 — Trading Execution
│   ├── portfolio/               # BC9 — Portfolio Management
│   ├── risk/                    # BC10 — Risk Management
│   ├── analytics/               # BC11 — Analytics & Reporting
│   ├── notifications/           # BC12 — Notifications
│   └── operations/              # BC13 — Administration & Operations
├── contracts/                   # Cross-context contracts (commands, events, queries)
├── shared/                      # Shared infrastructure utilities (no domain logic)
├── docs/
└── tests/
```

**Mapping rules:**

- Each service directory contains its domain model, application services, and
  infrastructure adapters — never shared with other contexts.
- Cross-context communication occurs only through `contracts/` artifacts.
- `shared/` contains only generic infrastructure (logging, configuration,
  observability) with no domain semantics.
- Shared domain models are avoided; duplication of small value types across
  context boundaries is preferred over shared ownership.

---

## 7. Future Scalability Considerations

1. **Context refinement:** Any context may decompose further — for example, Market
   Data may split into per-source collectors, or Trading Execution into paper and
   live execution sub-contexts.
2. **New data sources:** New providers are added inside Market Data as adapters
   without affecting other contexts.
3. **New execution venues:** Venue adapters are added inside Trading Execution;
   Strategy and Risk contracts remain unchanged.
4. **New analytical capabilities:** New analytics contexts (e.g., alternative
   prediction methodologies, advanced risk models) join as peers of existing
   contexts.
5. **Multi-tenancy:** Identity & Access can evolve to organizational tenancy
   without altering other contexts.
6. **Extraction to separate deployments:** As scale grows, any context can be
   physically extracted — contexts are bounded such that independent deployment
   is always possible.
7. **Contract evolution:** Contracts are versioned, enabling contexts to evolve
   at different rates.
8. **Research expansion:** AI Research & Training can add evaluation and
   experimentation capabilities without affecting production contexts.

---

## 8. Trade-offs

| Trade-off                                                                                                                        | Resolution                                                                                                                                                       |
| -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Context count vs. operational overhead** — thirteen contexts add coordination and infrastructure overhead in early milestones. | Logical boundaries are defined now; physical separation is introduced incrementally as complexity and scale justify it. Early milestones may co-deploy contexts. |
| **Data duplication vs. coupling** — contexts that consume data owned elsewhere may cache or copy data.                           | Duplication is preferred where it serves autonomy and performance; ownership of truth remains with the owning context.                                           |
| **Serving consistency vs. research velocity** — strict model serving controls can slow research iteration.                       | Prediction (serving) and AI Research & Training (experimentation) are deliberately separated so each can optimize for its own priorities.                        |
| **Centralized risk vs. path latency** — a mandatory risk gate adds latency to execution paths.                                   | Independent risk enforcement is non-negotiable for a trading platform; latency is managed through contract design, not by removing the gate.                     |
| **Generic vs. core contexts** — generic contexts (identity, notifications) could be replaced by external products.               | They are isolated behind contracts, so substitution remains possible without affecting core contexts.                                                            |
| **Shared kernel temptation** — contexts naturally want shared utility code.                                                      | Only non-semantic infrastructure is shared; domain concepts are never shared across boundaries.                                                                  |

---

## 9. Assumptions

1. The thirteen bounded contexts cover the platform's domain for the foreseeable
   future; refinement is expected, but new contexts are added only when cohesion
   demands it.
2. Each context's data model is owned exclusively by that context; no direct
   cross-context data access is permitted.
3. Cross-context communication follows the contract artifacts defined in the
   communication matrix; ad hoc point-to-point integration is prohibited.
4. Identity & Access Management is a generic context with authority over
   authorization — all other contexts consult it rather than implementing their
   own access policy.
5. Risk Management is the sole authority for risk decisions on execution paths;
   no context may bypass risk validation.
6. Market Data is the single acquisition point for external data — no other
   context integrates with external systems directly.
7. Logical boundaries defined here take precedence over physical deployment
   convenience; co-deployment in early milestones does not justify merging
   contexts.
8. Paper trading and live trading share the Trading Execution context by design,
   because they share order lifecycle mechanics; they may split if their
   operational requirements diverge.
