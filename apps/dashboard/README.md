# Research Dashboard

Next.js frontend for the AI Ethereum Market Analysis Platform — the operational
dashboard served from `apps/dashboard`. Architecture only: no charts, no AI,
no trading, no mock data.

## Stack

- Next.js 15 (App Router, typed routes) + React 19 + TypeScript (strict)
- Material UI v7 (dark-only theme, CSS variables)
- TanStack Query (data fetching, polling), Zustand (UI state)
- Axios (API client with interceptors), Zod (runtime validation)
- Vitest + Testing Library (unit/component tests)

## Run

```bash
pnpm install              # from the repo root (pnpm workspace)
pnpm --filter dashboard dev
```

Open <http://localhost:3000>. The root route redirects to `/dashboard`.

## Environment

Copy `apps/dashboard/.env.example` to `apps/dashboard/.env.local` and adjust:

| Variable               | Default                                    | Purpose                |
| ---------------------- | ------------------------------------------ | ---------------------- |
| `NEXT_PUBLIC_API_URL`  | `http://localhost:8000`                    | Backend API base URL   |
| `NEXT_PUBLIC_WS_URL`   | `wss://public-socket.india.delta.exchange` | Public Delta WS socket |
| `NEXT_PUBLIC_APP_NAME` | `Research Dashboard`                       | App/browser title      |

Variables are validated at startup by a Zod schema (`src/config/env.ts`);
invalid values fail fast with a clear message.

The API must allow the dashboard origin in `CORS_ORIGINS`, e.g.
`CORS_ORIGINS='["http://localhost:3000"]'` on the `services/api` side.

## Pages

| Route          | Purpose                                            |
| -------------- | -------------------------------------------------- |
| `/dashboard`   | Overview (placeholder)                             |
| `/markets`     | Market directory (placeholder)                     |
| `/historical`  | Candle history queries (placeholder)               |
| `/live-market` | Real-time trades/tickers/order books (placeholder) |
| `/research`    | AI workflows (placeholder)                         |
| `/settings`    | Preferences (placeholder)                          |
| `/health`      | Platform health dashboard (implemented)            |

### Health page

`/health` polls the backend system endpoints every 10 seconds:

- `GET /api/v1/system/health` — component status cards (API, database,
  Delta REST, Delta WebSocket, event bus, state manager)
- `GET /api/v1/system/status` — platform uptime (live-ticking), version,
  environment, last WebSocket message, last ingestion
- `GET /api/v1/system/metrics` — database statistics (markets, candles) and
  message processing statistics

Loading (skeleton), error (retry), and empty ("no data recorded yet") states
are handled. The page uses a dark, accessible MUI layout that is responsive
down to mobile.

## Testing

```bash
pnpm --filter dashboard test        # vitest run
pnpm --filter dashboard lint        # eslint (flat config, root baseline + next)
pnpm --filter dashboard typecheck   # tsc --noEmit
pnpm --filter dashboard build       # production build
```

Tests live next to the code (`*.test.ts(x)`): Zod schema validation for API
payloads and component tests for the health page (loading/error/empty/data
states with a mocked API module).

## Conventions

- Server components by default; `'use client'` only where interactivity is needed
- All API payloads validated with Zod schemas in `src/types/api/`
- Business logic lives in `src/features/<feature>/`; shared plumbing in `src/lib/`
- Prettier config inherited from the repo root; lint-staged runs the app ESLint
  for staged `apps/dashboard` files
