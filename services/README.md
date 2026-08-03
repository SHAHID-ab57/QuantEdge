# services/

One directory per bounded context — the platform's domain implementation.

## Future Contents

- `identity/` — BC1: Identity & Access Management
- `market-data/` — BC2: Market Data
- `features/` — BC3: Feature Engineering
- `research/` — BC4: AI Research & Training
- `prediction/` — BC5: Prediction
- `strategy/` — BC6: Strategy Management
- `backtesting/` — BC7: Backtesting
- `execution/` — BC8: Trading Execution
- `portfolio/` — BC9: Portfolio Management
- `risk/` — BC10: Risk Management
- `analytics/` — BC11: Analytics & Reporting
- `notifications/` — BC12: Notifications
- `operations/` — BC13: Administration & Operations

## Rules

- Each service owns its complete domain implementation exclusively.
- Cross-service communication occurs only through `packages/contracts/`.
- See `docs/architecture/DomainModel.md` for the bounded context design.
