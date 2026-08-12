# Environment Variable Reference

The canonical catalog of environment variables across the monorepo. Placeholder
values only — never commit real values.

This file documents the variables future services may consume. Every variable
belongs to a single domain prefix. See `configs/README.md` for the full
configuration strategy.

---

## Application

| Variable        | Required | Description        | Example                                           |
| --------------- | -------- | ------------------ | ------------------------------------------------- |
| `APP_ENV`       | Yes      | Active environment | `development` / `test` / `staging` / `production` |
| `APP_PORT`      | No       | HTTP port          | `8000`                                            |
| `APP_LOG_LEVEL` | No       | Logging verbosity  | `debug` / `info` / `warn` / `error`               |

## Database

| Variable       | Required | Description                  | Example                                             |
| -------------- | -------- | ---------------------------- | --------------------------------------------------- |
| `DB_URL`       | Yes      | PostgreSQL connection string | `postgresql://user:pass@postgres:5432/eth_platform` |
| `DB_POOL_SIZE` | No       | Connection pool size         | `10`                                                |
| `DB_TIMEOUT`   | No       | Connection timeout           | `5s`                                                |

## Redis

| Variable         | Required    | Description             | Example                          |
| ---------------- | ----------- | ----------------------- | -------------------------------- |
| `REDIS_URL`      | Yes         | Redis connection string | `redis://:password@redis:6379/0` |
| `REDIS_PASSWORD` | Conditional | Redis password          | —                                |
| `REDIS_TTL`      | No          | Default cache TTL       | `300`                            |

## Authentication

| Variable                 | Required | Description        | Example |
| ------------------------ | -------- | ------------------ | ------- |
| `JWT_SECRET`             | Yes      | JWT signing secret | —       |
| `JWT_EXPIRATION_MINUTES` | No       | Token lifetime     | `60`    |

## Delta Exchange India

| Variable                | Required    | Description                    | Example                             |
| ----------------------- | ----------- | ------------------------------ | ----------------------------------- |
| `DELTA_API_KEY`         | Conditional | API key                        | —                                   |
| `DELTA_API_SECRET`      | Conditional | API secret                     | —                                   |
| `DELTA_BASE_URL`        | No          | REST base URL                  | `https://api.india.delta.exchange`  |
| `DELTA_REQUEST_TIMEOUT` | No          | REST request timeout (seconds) | `10`                                |
| `DELTA_WEBSOCKET_URL`   | No          | WebSocket URL                  | `wss://socket.india.delta.exchange` |

## CoinGecko

| Variable             | Required | Description | Example                            |
| -------------------- | -------- | ----------- | ---------------------------------- |
| `COINGECKO_API_KEY`  | Optional | API key     | —                                  |
| `COINGECKO_BASE_URL` | No       | Base URL    | `https://api.coingecko.com/api/v3` |

## Marketaux

| Variable             | Required    | Description | Example                     |
| -------------------- | ----------- | ----------- | --------------------------- |
| `MARKETAUX_API_KEY`  | Conditional | API key     | —                           |
| `MARKETAUX_BASE_URL` | No          | Base URL    | `https://api.marketaux.com` |

## Etherscan

| Variable             | Required    | Description | Example                    |
| -------------------- | ----------- | ----------- | -------------------------- |
| `ETHERSCAN_API_KEY`  | Conditional | API key     | —                          |
| `ETHERSCAN_BASE_URL` | No          | Base URL    | `https://api.etherscan.io` |

## FRED

| Variable        | Required    | Description | Example                           |
| --------------- | ----------- | ----------- | --------------------------------- |
| `FRED_API_KEY`  | Conditional | API key     | —                                 |
| `FRED_BASE_URL` | No          | Base URL    | `https://api.stlouisfed.org/fred` |

## DefiLlama

| Variable             | Required | Description | Example                |
| -------------------- | -------- | ----------- | ---------------------- |
| `DEFILLAMA_BASE_URL` | No       | Base URL    | `https://api.llama.fi` |

## OpenAI

| Variable         | Required    | Description      | Example  |
| ---------------- | ----------- | ---------------- | -------- |
| `OPENAI_API_KEY` | Conditional | API key          | —        |
| `OPENAI_MODEL`   | No          | Model identifier | `gpt-4o` |

## Logging

| Variable     | Required | Description        | Example         |
| ------------ | -------- | ------------------ | --------------- |
| `LOG_LEVEL`  | No       | Log level          | `info`          |
| `LOG_FORMAT` | No       | Output format      | `json` / `text` |
| `LOG_OUTPUT` | No       | Output destination | `stdout`        |

## AI / ML Services

| Variable            | Required | Description                   | Example                 |
| ------------------- | -------- | ----------------------------- | ----------------------- |
| `AI_MODEL_DIR`      | No       | Model artifact directory      | `artifacts/models`      |
| `AI_BATCH_SIZE`     | No       | Training/inference batch size | `256`                   |
| `AI_EXPERIMENT_DIR` | No       | Experiment output directory   | `artifacts/experiments` |

## Feature Pipeline

| Variable             | Required    | Description                    | Example |
| -------------------- | ----------- | ------------------------------ | ------- |
| `FEATURE_STORE_URL`  | Conditional | Feature store endpoint         | —       |
| `FEATURE_BATCH_SIZE` | No          | Feature computation batch size | `10000` |

## Notifications (SMTP)

| Variable        | Required    | Description   | Example |
| --------------- | ----------- | ------------- | ------- |
| `SMTP_HOST`     | Conditional | SMTP server   | —       |
| `SMTP_PORT`     | No          | SMTP port     | `587`   |
| `SMTP_USER`     | Conditional | SMTP user     | —       |
| `SMTP_PASSWORD` | Conditional | SMTP password | —       |

## Object Storage

| Variable                    | Required    | Description      | Example |
| --------------------------- | ----------- | ---------------- | ------- |
| `OBJECT_STORAGE_ENDPOINT`   | Conditional | Storage endpoint | —       |
| `OBJECT_STORAGE_BUCKET`     | Conditional | Default bucket   | —       |
| `OBJECT_STORAGE_ACCESS_KEY` | Conditional | Access key       | —       |
| `OBJECT_STORAGE_SECRET_KEY` | Conditional | Secret key       | —       |

---

## Notes

- **Conditional** means required only when the associated feature is enabled.
- Secrets (`*_KEY`, `*_SECRET`, `*_PASSWORD`, `JWT_SECRET`) never appear in
  committed files.
- Templates: root `.env.example`, `infra/docker/.env.example`.
- See `configs/README.md` for naming, hierarchy, loading, validation, and
  secrets policies.
