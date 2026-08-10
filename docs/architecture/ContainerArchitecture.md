# Container Architecture (C4 Model – Level 2)

## Document Information

**Document:** Container Architecture — C4 Model, Level 2

**Scope:** Logical decomposition of the platform into major deployable containers

**Status:** Draft

---

## 1. Container Overview

The platform decomposes into the following major containers. Each container is an
independently deployable unit with a well-defined responsibility, communicating with
other containers through explicit interfaces.

| #   | Container                      | Category        | Summary                                                     |
| --- | ------------------------------ | --------------- | ----------------------------------------------------------- |
| C1  | Web Frontend                   | Presentation    | User interfaces for all actor roles.                        |
| C2  | Backend API                    | Application     | Primary service boundary exposing platform capabilities.    |
| C3  | Authentication Service         | Application     | Identity, authentication, and authorization.                |
| C4  | Market Data Collector          | Data Ingestion  | Retrieves and normalizes data from external sources.        |
| C5  | Streaming Service              | Data Ingestion  | Distributes live market data to interested consumers.       |
| C6  | Data Processing Pipeline       | Data Processing | Validates, transforms, and stores raw and processed data.   |
| C7  | Feature Store                  | Data Storage    | Stores and serves versioned computed features.              |
| C8  | AI Research & Training Service | Analytics       | Model development, training, and experiment management.     |
| C9  | Prediction Service             | Analytics       | Produces probabilistic forecasts from trained models.       |
| C10 | Backtesting Engine             | Analytics       | Simulates strategy performance on historical data.          |
| C11 | Strategy Engine                | Analytics       | Defines, manages, and evaluates trading strategies.         |
| C12 | Risk Engine                    | Analytics       | Computes risk metrics, limits, and scenario analyses.       |
| C13 | Portfolio Service              | Analytics       | Manages portfolios, positions, and performance analytics.   |
| C14 | Trading Execution Service      | Execution       | Manages simulated and live order execution.                 |
| C15 | Notification Service           | Application     | Delivers alerts and notifications to users.                 |
| C16 | Scheduler / Job Runner         | Infrastructure  | Orchestrates scheduled and recurring workloads.             |
| C17 | Monitoring & Logging Service   | Infrastructure  | Collects metrics, logs, and traces; supports observability. |
| C18 | Relational Database            | Data Storage    | Primary transactional and domain data store.                |
| C19 | Cache                          | Data Storage    | In-memory cache for high-throughput, low-latency access.    |
| C20 | Object Storage                 | Data Storage    | Durable storage for large artifacts and files.              |
| C21 | Message Broker                 | Infrastructure  | Asynchronous communication backbone between containers.     |

The container set is a logical decomposition. Some containers may be physically
co-located in early milestones; the logical boundaries remain the contract for
future physical deployment decisions.

---

## 2. Container Responsibilities

### C1 — Web Frontend

- **Purpose:** Provide the user-facing interface for all platform capabilities.
- **Primary responsibilities:** Render dashboards, research workspaces, strategy
  management, portfolio views, and administration screens; handle user interaction;
  communicate with the Backend API.
- **Data consumed:** Aggregated analytical outputs, predictions, reports, and
  configuration views via the Backend API.
- **Data produced:** User requests, form submissions, and interactive queries.
- **Main interactions:** Backend API (request/response); Authentication Service
  (login sessions).
- **Why it exists:** Separates presentation from domain logic, enabling independent
  evolution of the interface and the platform core.
- **Future scalability:** Can be split into role-specific applications or a mobile
  interface without affecting backend containers.

### C2 — Backend API

- **Purpose:** The primary service boundary through which all user-facing capabilities
  are exposed.
- **Primary responsibilities:** Implement application use cases; orchestrate container
  interactions; enforce authorization; validate and route requests; expose consistent
  interfaces to the frontend and integrations.
- **Data consumed:** Domain data from the Relational Database; computed features from
  the Feature Store; forecasts from the Prediction Service.
- **Data produced:** API responses, write operations to domain stores, and commands
  to downstream containers.
- **Main interactions:** Web Frontend, Authentication Service, Feature Store,
  Prediction Service, Strategy Engine, Portfolio Service, Risk Engine, Relational
  Database, Cache, Message Broker.
- **Why it exists:** Provides a single, consistent entry point that protects the
  platform's internal containers from direct exposure.
- **Future scalability:** Stateless by design; scales horizontally as user and
  request volumes grow.

### C3 — Authentication Service

- **Purpose:** Manage identities, sessions, and access control across the platform.
- **Primary responsibilities:** Authenticate users; issue and validate credentials and
  sessions; enforce role-based access decisions; manage user accounts and roles.
- **Data consumed:** User records from the Relational Database; authentication requests.
- **Data produced:** Authentication tokens, session state, authorization decisions.
- **Main interactions:** Web Frontend, Backend API, Relational Database.
- **Why it exists:** Centralizes identity and security policy in a single auditable
  container.
- **Future scalability:** Supports federation and multi-factor mechanisms as security
  requirements evolve.

### C4 — Market Data Collector

- **Purpose:** Retrieve market, on-chain, sentiment, and macroeconomic data from
  external systems.
- **Primary responsibilities:** Poll and pull data from external providers; normalize
  and standardize incoming records; handle provider outages, rate limits, and
  retries; publish raw data for processing.
- **Data consumed:** External system APIs and feeds.
- **Data produced:** Normalized raw market data records.
- **Main interactions:** Message Broker, Data Processing Pipeline, Trading Execution
  Service (order/position reconciliation), external systems.
- **Why it exists:** Isolates external integration complexity — provider quirks,
  rate limits, and schema differences — from the rest of the platform.
- **Future scalability:** Each external source can be supported by an independent
  collector instance or adapter without affecting other containers.

### C5 — Streaming Service

- **Purpose:** Distribute live market data to consumers in near real time.
- **Primary responsibilities:** Subscribe to live data feeds; maintain subscription
  state; publish market events to interested containers; buffer data during
  consumer backpressure.
- **Data consumed:** Live market events from external providers (via the Market Data
  Collector).
- **Data produced:** Low-latency market event streams.
- **Main interactions:** Message Broker, Feature Store, Prediction Service, Trading
  Execution Service.
- **Why it exists:** Decouples producers from consumers of real-time data, allowing
  consumers to evolve independently.
- **Future scalability:** Scales by partitioning event streams and adding consumer
  groups as demand grows.

### C6 — Data Processing Pipeline

- **Purpose:** Validate, transform, and persist all data entering the platform.
- **Primary responsibilities:** Validate completeness and consistency; deduplicate;
  transform into canonical forms; load data into the Relational Database, Object
  Storage, and Feature Store; compute derived datasets.
- **Data consumed:** Raw records from the Message Broker and Object Storage.
- **Data produced:** Cleaned and curated data artifacts.
- **Main interactions:** Market Data Collector, Message Broker, Relational Database,
  Object Storage, Feature Store, Scheduler / Job Runner.
- **Why it exists:** Centralizes data quality enforcement — the foundation of all
  downstream analytical validity.
- **Future scalability:** Supports batch and incremental processing modes that can be
  scaled independently.

### C7 — Feature Store

- **Purpose:** Compute, store, and serve versioned features for training and inference.
- **Primary responsibilities:** Compute features consistently from raw data; store
  feature definitions and values with versioning; serve features at training time
  (historical) and inference time (real time); enforce feature consistency across
  environments.
- **Data consumed:** Curated data from the Data Processing Pipeline; live data from
  the Streaming Service.
- **Data produced:** Versioned feature values and definitions.
- **Main interactions:** Data Processing Pipeline, AI Research & Training Service,
  Prediction Service, Backtesting Engine, Message Broker.
- **Why it exists:** Prevents training/serving skew — the most common source of
  silent model degradation — by centralizing feature computation.
- **Future scalability:** Supports online/offline serving tiers that scale
  independently as research and production workloads diverge.

### C8 — AI Research & Training Service

- **Purpose:** Support the full model development lifecycle.
- **Primary responsibilities:** Manage experiment configurations; train and evaluate
  models; track experiments and model artifacts; register approved models for
  serving; document results.
- **Data consumed:** Versioned datasets from the Feature Store and Object Storage.
- **Data produced:** Model artifacts, experiment records, evaluation reports.
- **Main interactions:** Feature Store, Prediction Service, Object Storage,
  Relational Database, Scheduler / Job Runner.
- **Why it exists:** Isolates computationally heavy research workloads from
  production serving, protecting both from interference.
- **Future scalability:** Training workloads can scale on dedicated compute pools
  while production serving remains stable.

### C9 — Prediction Service

- **Purpose:** Produce probabilistic forecasts from registered models.
- **Primary responsibilities:** Load registered models; serve batch and real-time
  predictions; apply uncertainty quantification; log predictions with full
  provenance; support model version pinning and rollback.
- **Data consumed:** Features from the Feature Store; live signals from the
  Streaming Service.
- **Data produced:** Probabilistic forecasts — distributions, intervals, scenarios.
- **Main interactions:** Feature Store, AI Research & Training Service, Backend API,
  Backtesting Engine, Strategy Engine, Relational Database, Message Broker.
- **Why it exists:** Provides a stable serving boundary that allows models to be
  updated without affecting consumers.
- **Future scalability:** Scales horizontally for low-latency inference; supports
  model canary and shadow deployments.

### C10 — Backtesting Engine

- **Purpose:** Evaluate strategies and models against historical data under realistic
  conditions.
- **Primary responsibilities:** Simulate strategy execution on historical data;
  account for data availability, slippage, and fees; produce performance metrics;
  support walk-forward and scenario-based validation.
- **Data consumed:** Historical data from the Relational Database and Object Storage;
  features from the Feature Store; predictions from the Prediction Service.
- **Data produced:** Backtest results, performance reports, validation metrics.
- **Main interactions:** Feature Store, Prediction Service, Strategy Engine,
  Relational Database, Scheduler / Job Runner.
- **Why it exists:** Centralizes simulation rigor, ensuring that performance claims
  are produced under consistent, auditable conditions.
- **Future scalability:** Simulation workloads can be parallelized across
  independent compute units.

### C11 — Strategy Engine

- **Purpose:** Define, manage, and evaluate trading strategies.
- **Primary responsibilities:** Manage strategy definitions and configuration; translate
  strategies into executable logic for backtesting and paper trading; monitor strategy
  performance; enforce strategy-level risk constraints.
- **Data consumed:** Predictions from the Prediction Service; risk metrics from the
  Risk Engine; portfolio state from the Portfolio Service.
- **Data produced:** Strategy signals and execution requests.
- **Main interactions:** Prediction Service, Risk Engine, Portfolio Service,
  Backtesting Engine, Trading Execution Service, Backend API.
- **Why it exists:** Keeps strategy logic — an evolving research artifact — isolated
  from execution mechanics.
- **Future scalability:** New strategy types can be added as pluggable components
  without changing execution or risk containers.

### C12 — Risk Engine

- **Purpose:** Quantify and enforce risk across the platform.
- **Primary responsibilities:** Compute risk metrics — volatility, drawdown, value at
  risk, tail risk; run scenario and stress analyses; enforce pre-trade and
  post-trade risk limits; produce risk reports.
- **Data consumed:** Portfolio state, market data, predictions, and order intents.
- **Data produced:** Risk metrics, limit checks, scenario assessments.
- **Main interactions:** Portfolio Service, Strategy Engine, Trading Execution
  Service, Prediction Service, Backend API, Relational Database.
- **Why it exists:** Centralizes risk policy so that all execution paths are subject
  to consistent controls.
- **Future scalability:** Risk computations can be extended to new asset classes and
  risk models without affecting other containers.

### C13 — Portfolio Service

- **Purpose:** Manage portfolios, positions, and performance analytics.
- **Primary responsibilities:** Maintain portfolio composition; track positions and
  balances; compute portfolio performance; generate analytics and attribution;
  record paper and live trading activity.
- **Data consumed:** Execution records, market data, and risk metrics.
- **Data produced:** Portfolio state, performance analytics, and position records.
- **Main interactions:** Trading Execution Service, Risk Engine, Backend API,
  Relational Database, Cache.
- **Why it exists:** Provides a single authoritative view of portfolio state that
  decouples analytics from execution mechanics.
- **Future scalability:** Supports multiple portfolios, asset classes, and accounting
  methodologies as requirements grow.

### C14 — Trading Execution Service

- **Purpose:** Manage the lifecycle of simulated and live orders.
- **Primary responsibilities:** Accept order intents from strategies; validate against
  risk limits; submit orders to exchanges for live trading; simulate fills for paper
  trading; reconcile execution state; manage retries and failure handling.
- **Data consumed:** Order intents, risk decisions, exchange account state.
- **Data produced:** Order records, execution confirmations, position updates.
- **Main interactions:** Strategy Engine, Risk Engine, Portfolio Service, Market Data
  Collector, external exchanges, Message Broker.
- **Why it exists:** Isolates execution mechanics — venue protocols, order types, and
  reconciliation — from strategy and research logic.
- **Future scalability:** Supports additional execution venues and order types by
  extending the execution layer independently.

### C15 — Notification Service

- **Purpose:** Deliver alerts and notifications to users.
- **Primary responsibilities:** Manage notification preferences; compose and deliver
  messages — alerts, reports, system events; track delivery state.
- **Data consumed:** Alert events from the Monitoring & Logging Service, Risk Engine,
  and Backend API.
- **Data produced:** Delivered notifications.
- **Main interactions:** Backend API, Monitoring & Logging Service, Risk Engine.
- **Why it exists:** Separates notification policy and delivery channels from the
  containers that generate events.
- **Future scalability:** New channels (in-app, email, push) can be added without
  touching event producers.

### C16 — Scheduler / Job Runner

- **Purpose:** Orchestrate scheduled and recurring workloads.
- **Primary responsibilities:** Schedule recurring jobs — data collection, training,
  backtests, report generation, maintenance; manage job queues; monitor job
  execution and failures; coordinate workflows across containers.
- **Data consumed:** Job definitions and execution history.
- **Data produced:** Job invocations and execution records.
- **Main interactions:** Market Data Collector, Data Processing Pipeline, AI Research
  & Training Service, Backtesting Engine, Notification Service, Relational Database.
- **Why it exists:** Centralizes orchestration so that timing and sequencing logic is
  not embedded in individual containers.
- **Future scalability:** Supports distributed job execution as workload volume
  grows.

### C17 — Monitoring & Logging Service

- **Purpose:** Provide observability across the entire platform.
- **Primary responsibilities:** Collect metrics, logs, and traces from all containers;
  store and index observability data; detect anomalies and produce alerts; support
  dashboards and operational querying.
- **Data consumed:** Telemetry from every container.
- **Data produced:** Metrics, logs, traces, alerts, dashboards.
- **Main interactions:** All containers (telemetry collection); Notification Service
  (alerts); Backend API (operational views).
- **Why it exists:** Centralizes observability so that operational insight is uniform
  across heterogeneous containers.
- **Future scalability:** Telemetry storage scales independently from the platform's
  functional containers.

### C18 — Relational Database

- **Purpose:** Primary transactional and domain data store.
- **Primary responsibilities:** Persist domain entities — users, strategies,
  portfolios, orders, predictions, experiment metadata; enforce data integrity and
  consistency; support transactional workloads.
- **Data consumed:** Writes from application containers.
- **Data produced:** Reliable queryable domain state.
- **Main interactions:** Backend API, Authentication Service, Portfolio Service,
  Risk Engine, AI Research & Training Service, Scheduler / Job Runner.
- **Why it exists:** Provides the consistency guarantees required for domain
  correctness.
- **Future scalability:** Read replicas and partitioning can be introduced as query
  and write volumes grow.

### C19 — Cache

- **Purpose:** Provide low-latency access to hot data.
- **Primary responsibilities:** Cache frequently accessed data — reference data,
  session state, recent predictions, feature snapshots; enforce invalidation and
  eviction policies.
- **Data consumed:** Read-through requests from application containers.
- **Data produced:** High-speed data access.
- **Main interactions:** Backend API, Portfolio Service, Prediction Service.
- **Why it exists:** Reduces latency and database load for high-frequency read
  paths.
- **Future scalability:** Scales horizontally with partitioning for cache capacity.

### C20 — Object Storage

- **Purpose:** Durable storage for large artifacts.
- **Primary responsibilities:** Store raw data archives, datasets, model artifacts,
  experiment outputs, and report files; provide lifecycle and retention policies.
- **Data consumed:** Large binary and bulk data from pipeline and research
  containers.
- **Data produced:** Durable artifacts for retrieval and archival.
- **Main interactions:** Data Processing Pipeline, AI Research & Training Service,
  Backtesting Engine, Relational Database (metadata references).
- **Why it exists:** Provides cost-effective, scalable storage for data that does
  not require transactional semantics.
- **Future scalability:** Storage capacity scales elastically with minimal
  operational effort.

### C21 — Message Broker

- **Purpose:** Asynchronous communication backbone.
- **Primary responsibilities:** Transport events between containers; decouple
  producers from consumers; buffer data under load; support delivery guarantees
  and retry semantics.
- **Data consumed:** Events published by containers.
- **Data produced:** Reliable event delivery to subscribers.
- **Main interactions:** Market Data Collector, Streaming Service, Data Processing
  Pipeline, Feature Store, Prediction Service, Trading Execution Service,
  Notification Service.
- **Why it exists:** Enables loose coupling — producers are not blocked by consumer
  availability or throughput.
- **Future scalability:** Scales through partitioning and consumer group expansion.

---

## 3. Communication Between Containers

Communication follows two principal patterns:

| Pattern                            | Description                                                                                | Example Paths                                                                                                                                                                                               |
| ---------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Synchronous (request/response)** | Direct invocation for operations requiring immediate results.                              | Web Frontend ↔ Backend API; Backend API ↔ Feature Store / Prediction Service / Portfolio Service; Authentication Service ↔ Relational Database.                                                             |
| **Asynchronous (event-driven)**    | Event publication and consumption for decoupled, high-throughput, and scheduled workloads. | Market Data Collector → Message Broker → Data Processing Pipeline → Feature Store; Streaming Service → Prediction Service; Strategy Engine → Trading Execution Service; Risk Engine → Notification Service. |

**Communication rules:**

- Containers communicate only through defined interfaces; no shared state or direct
  database access across container boundaries.
- Event-driven paths are preferred for data flows where latency tolerance allows it,
  preserving loose coupling.
- Synchronous paths are used only where a caller requires a direct response.
- All cross-container calls flow through the Message Broker or the Backend API;
  containers do not form ad hoc point-to-point connections.

---

## 4. High-Level Data Flow

**Ingestion path:**

1. Market Data Collector retrieves data from external systems.
2. Raw data is published to the Message Broker.
3. Data Processing Pipeline validates, transforms, and persists raw data to
   Relational Database and Object Storage.
4. Feature Store computes and versions features from curated data; live features
   are computed from Streaming Service events.

**Research path:**

5. AI Research & Training Service pulls versioned datasets from the Feature Store
   and trains models; artifacts are stored in Object Storage and registered in the
   Relational Database.
6. Approved models are deployed to the Prediction Service.

**Inference path:**

7. Prediction Service consumes features and produces probabilistic forecasts.
8. Forecasts are published to the Message Broker and persisted.

**Decision path:**

9. Strategy Engine consumes forecasts, risk metrics, and portfolio state to produce
   strategy signals.
10. Risk Engine validates order intents against risk limits.
11. Trading Execution Service executes approved intents — simulated fills for paper
    trading, exchange submission for live trading — and reports executions to the
    Portfolio Service.

**Presentation path:**

12. Backend API composes results from domain stores and analytical containers and
    serves them to the Web Frontend.

**Observability path:**

13. All containers emit telemetry to the Monitoring & Logging Service, which
    produces alerts and operational views.

---

## 5. Mermaid C4 Container Diagram

```mermaid
C4Container
    title Container Diagram — AI-Powered Ethereum Market Analysis and Probabilistic Prediction Platform

    Person(admin, "Administrator", "Manages platform, users, and system health")
    Person(researcher, "Researcher", "Conducts quantitative research and model development")
    Person(trader, "Trader", "Validates strategies and manages orders")
    Person(analyst, "Analyst", "Consumes analysis and reports")

    System_Boundary(platform, "Ethereum Market Analysis and Probabilistic Prediction Platform") {

        Container(web, "Web Frontend", "SPA / Web Application",
            "User interfaces for all roles")
        Container(api, "Backend API", "Application Service",
            "Exposes platform capabilities via consistent interfaces")
        Container(auth, "Authentication Service", "Application Service",
            "Identity, sessions, role-based access control")

        Container(collector, "Market Data Collector", "Data Ingestion",
            "Retrieves and normalizes data from external systems")
        Container(streaming, "Streaming Service", "Data Ingestion",
            "Distributes live market data")
        Container(pipeline, "Data Processing Pipeline", "Data Processing",
            "Validates, transforms, persists data")
        Container(features, "Feature Store", "Data Storage",
            "Computes and serves versioned features")

        Container(training, "AI Research & Training Service", "Analytics",
            "Model development, training, experiment tracking")
        Container(prediction, "Prediction Service", "Analytics",
            "Produces probabilistic forecasts")
        Container(backtest, "Backtesting Engine", "Analytics",
            "Simulates strategies on historical data")
        Container(strategy, "Strategy Engine", "Analytics",
            "Defines and evaluates strategies")
        Container(risk, "Risk Engine", "Analytics",
            "Quantifies and enforces risk limits")
        Container(portfolio, "Portfolio Service", "Analytics",
            "Manages portfolios and performance")

        Container(execution, "Trading Execution Service", "Execution",
            "Simulated and live order execution")

        Container(notifications, "Notification Service", "Application",
            "Delivers alerts and notifications")
        Container(scheduler, "Scheduler / Job Runner", "Infrastructure",
            "Orchestrates scheduled workloads")
        Container(monitoring, "Monitoring & Logging Service", "Infrastructure",
            "Metrics, logs, traces, alerts")

        ContainerDb(db, "Relational Database", "Data Storage",
            "Transactional domain data")
        ContainerDb(cache, "Cache", "Data Storage",
            "Low-latency data access")
        ContainerDb(objects, "Object Storage", "Data Storage",
            "Large artifacts and archives")
        ContainerDb(broker, "Message Broker", "Infrastructure",
            "Asynchronous event transport")

        Rel(admin, web, "Administers", "HTTPS")
        Rel(researcher, web, "Researches, trains models", "HTTPS")
        Rel(trader, web, "Manages strategies and orders", "HTTPS")
        Rel(analyst, web, "Reviews analysis and reports", "HTTPS")

        Rel(web, api, "API requests", "HTTPS")
        Rel(web, auth, "Login", "HTTPS")
        Rel(auth, api, "Authorize requests", "HTTPS")

        Rel(api, features, "Read features", "Sync")
        Rel(api, prediction, "Request forecasts", "Sync")
        Rel(api, portfolio, "Manage portfolios", "Sync")
        Rel(api, strategy, "Manage strategies", "Sync")
        Rel(api, risk, "Request risk metrics", "Sync")
        Rel(api, db, "Domain reads/writes", "SQL")
        Rel(api, cache, "Cache access", "Sync")

        Rel(collector, broker, "Publish raw data", "Events")
        Rel(collector, execution, "Reconciliation data", "Sync")
        Rel(broker, pipeline, "Consume raw data", "Events")
        Rel(pipeline, db, "Persist curated data", "SQL")
        Rel(pipeline, objects, "Archive raw data", "IO")
        Rel(pipeline, features, "Feed curated data", "Sync")

        Rel(streaming, broker, "Publish live events", "Events")
        Rel(broker, features, "Live feature events", "Events")
        Rel(features, training, "Training features", "Batch")
        Rel(features, prediction, "Inference features", "Sync")
        Rel(features, backtest, "Historical features", "Batch")

        Rel(training, objects, "Store model artifacts", "IO")
        Rel(training, db, "Experiment records", "SQL")
        Rel(training, prediction, "Deploy models", "Sync")

        Rel(prediction, broker, "Publish forecasts", "Events")
        Rel(prediction, strategy, "Serve forecasts", "Sync")
        Rel(strategy, backtest, "Backtest strategies", "Sync")
        Rel(strategy, risk, "Pre-trade checks", "Sync")
        Rel(strategy, execution, "Order intents", "Sync")
        Rel(execution, portfolio, "Execution updates", "Events")
        Rel(risk, portfolio, "Risk metrics", "Sync")
        Rel(risk, execution, "Risk decisions", "Sync")

        Rel(scheduler, collector, "Schedule collection", "Invoke")
        Rel(scheduler, pipeline, "Schedule processing", "Invoke")
        Rel(scheduler, training, "Schedule training", "Invoke")
        Rel(scheduler, backtest, "Schedule backtests", "Invoke")

        Rel(monitoring, broker, "Telemetry events", "Events")
        Rel(monitoring, notifications, "Alerts", "Sync")
        Rel(notifications, web, "Deliver notifications", "Push")

        UpdateElementStyle(platform, $bgColor="#F4F6F8")
    }

    System_Ext(delta, "Delta Exchange India",
        "Market data and trade execution venue")
    System_Ext(coinGecko, "CoinGecko", "Aggregated market statistics")
    System_Ext(marketaux, "Marketaux", "News and sentiment data")
    System_Ext(etherscan, "Etherscan", "On-chain data")
    System_Ext(fred, "FRED", "Macroeconomic time series")
    System_Ext(altme, "Alternative.me", "Fear & Greed Index")
    System_Ext(defillama, "DefiLlama", "DeFi metrics")

    Rel(collector, delta, "Pulls market data", "API")
    Rel(execution, delta, "Submits orders; reconciles", "API")
    Rel(collector, coinGecko, "Pulls market stats", "API")
    Rel(collector, marketaux, "Pulls news/sentiment", "API")
    Rel(collector, etherscan, "Pulls on-chain data", "API")
    Rel(collector, fred, "Pulls macro data", "API")
    Rel(collector, altme, "Pulls sentiment index", "API")
    Rel(collector, defillama, "Pulls DeFi metrics", "API")
```

---

## 6. Architecture Decisions

| ADR Ref | Decision                                                                                       | Rationale                                                                                                                               |
| ------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| AD-1    | Asynchronous event-driven communication via a Message Broker for data flows.                   | Decouples producers from consumers; tolerates load spikes and consumer failures; enables independent scaling.                           |
| AD-2    | Synchronous request/response only where immediate results are required.                        | Minimizes coupling while preserving usability where callers need direct answers.                                                        |
| AD-3    | Feature computation centralized in a Feature Store.                                            | Prevents training/serving skew; guarantees feature consistency across research and production.                                          |
| AD-4    | Research and training isolated from production serving.                                        | Heavy computational workloads must not affect prediction latency or availability.                                                       |
| AD-5    | Execution, strategy, and risk logic separated into distinct containers.                        | Enforces that no order can be placed without passing independent risk validation; enables strategy evolution without execution changes. |
| AD-6    | All external integrations confined to the Market Data Collector and Trading Execution Service. | Isolates provider variability to two integration points; keeps the rest of the platform provider-agnostic.                              |
| AD-7    | Observability centralized in a dedicated container.                                            | Provides uniform operational insight across heterogeneous containers.                                                                   |
| AD-8    | Containers communicate only through defined interfaces; no cross-container shared state.       | Preserves loose coupling and independent deployability.                                                                                 |
| AD-9    | Data storage split by access pattern — transactional, cached, object, event transport.         | Each store is optimized for its workload; enables independent scaling and lifecycle policies.                                           |
| AD-10   | Scheduler centralizes all recurring workload orchestration.                                    | Timing and sequencing logic is not embedded in individual containers.                                                                   |

---

## 7. Assumptions

1. The logical container boundaries defined here remain stable even as physical
   deployment evolves from a single host to distributed infrastructure.
2. Data volumes warrant dedicated ingestion, storage, and feature infrastructure but
   do not yet require geographically distributed deployment.
3. The platform's user base and analytical workloads grow gradually, allowing
   incremental scaling rather than anticipatory over-provisioning.
4. External systems continue to provide data via network interfaces with rate
   limits, outages, and schema variability that the platform must absorb.
5. Asynchronous delivery is acceptable for non-interactive data flows.
6. The number of concurrent users at any stage is modest relative to the platform's
   scaling headroom.
7. No container requires real-time guarantees stricter than those achievable with
   the stated communication patterns.

---

## 8. Future Expansion Considerations

1. **Container decomposition:** Any container may decompose into finer-grained
   services as complexity grows — for example, the Backend API may split by domain,
   or the Data Processing Pipeline by data source.
2. **Streaming scale:** The Streaming Service and Message Broker can scale through
   partitioning as live data volumes increase.
3. **Training scale:** AI Research & Training workloads can be offloaded to
   dedicated compute infrastructure without architectural change.
4. **Additional markets and asset classes:** New data sources can be added through
   additional Market Data Collector adapters; new execution venues through Trading
   Execution Service extensions.
5. **Multi-tenancy:** The Authentication Service and Backend API can evolve to
   support organizational tenancy and finer-grained authorization.
6. **Advanced analytics:** New analytical containers — for example, alternative
   prediction methods or advanced risk models — can be added as peers to existing
   analytics containers.
7. **Compliance and audit:** Additional audit and reporting containers can be
   introduced without altering existing container responsibilities.
8. **Deployment topology:** Physical deployment decisions — host, container, or
   cluster placement — are deferred and will be addressed in the Deployment View.
