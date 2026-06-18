# Aegis Trading Engine

An event-driven crypto trading backend that streams **live BTC prices** from Binance, lets users register, fund a test wallet, and execute server-authoritative trades against the live market price.

Built as a portfolio / interview demo to showcase async Python, message-driven architecture, and containerized microservices.

---

## Table of Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Quick start (run the whole thing in one command)](#quick-start)
- [Exploring the API (the "site")](#exploring-the-api)
- [API reference](#api-reference)
- [Environment variables](#environment-variables)
- [Project layout](#project-layout)
- [Tech stack](#tech-stack)

---

## What it does

```
Binance live BTC stream
        │  (WebSocket)
        ▼
 ingestion-gateway (Node/TS) ──publishes──► RabbitMQ "market-data" (fanout)
                                                    │
                                                    ▼
                                      execution-engine worker (Python)
                                                    │  writes live price
                                                    ▼
                                                  Redis
                                                    │  read on every request
                                                    ▼
                                FastAPI  /api/v1/...  (the REST API)
```

The trade price is **always** taken from Redis (server-side), never trusted from the client — so a user can't spoof a favorable price.

---

## Architecture

Six services, all wired together by `docker-compose.yml`:

| Service     | Tech            | Role |
|-------------|-----------------|------|
| `gateway`   | Node.js / TS    | Streams live BTC/USD price from Binance → RabbitMQ |
| `rabbitmq`  | RabbitMQ        | Fanout message bus (mgmt UI on :15672) |
| `worker`    | Python          | Consumes RabbitMQ → caches live price in Redis |
| `redis`     | Redis           | Ultra-fast price cache + rate-limit counters |
| `api`       | Python / FastAPI| REST API: auth, portfolio, trading, market |
| `postgres`  | PostgreSQL      | Users, portfolios, transaction ledger |

---

## Quick start

> You only need **Docker Desktop** installed. Nothing else.

### 1. Create your `.env`

Copy the example and (optionally) change the secret:

```bash
cp .env.example .env
```

### 2. Launch everything

```bash
docker compose up --build
```

Wait until you see the API and gateway logs settle. That's it — all six services are running.

### 3. Open the interactive docs

👉 **http://localhost:8000/docs**

This is the Swagger UI — the easiest way to navigate and try every endpoint from your browser. See the [walkthrough](#exploring-the-api) below.

### 4. Shut down when done

```bash
docker compose down          # stop containers
docker compose down -v       # stop AND wipe the database/redis volumes
```

---

## Exploring the API

Open **http://localhost:8000/docs** and follow this flow to see the whole app work end-to-end:

1. **`POST /api/v1/auth/register`** — create a user with an email + password.
2. **`POST /api/v1/auth/login`** — log in. Copy the `access_token` from the response.
3. Click the green **`Authorize`** button (top right of Swagger) and paste the token. Now you're authenticated for the protected endpoints.
4. **`POST /api/v1/trading/faucet`** — fund your test account with $100,000 fake USD.
5. **`GET /api/v1/market/price/BTC-USD`** — see the **live** BTC price coming straight from Binance.
6. **`POST /api/v1/trading/execute`** — buy some BTC:
   ```json
   { "type": "BUY", "pair": "BTC-USD", "amount": 0.1 }
   ```
7. **`GET /api/v1/trading/portfolio`** — watch your USD go down and BTC go up.

`GET /health` is a no-auth health check (handy for load balancers / demos).

---

## API reference

Base path: `/api/v1`

### Authentication
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register` | – | Register with email + password |
| `POST` | `/auth/login`    | – | Returns a JWT (valid 7 days) |

### Trading & Portfolio
| Method | Path | Auth | Description | Rate limit |
|--------|------|------|-------------|------------|
| `GET`  | `/trading/portfolio` | ✅ | List your asset balances | – |
| `POST` | `/trading/faucet`    | ✅ | Fund account with $100k test USD | 1 / 60s |
| `POST` | `/trading/execute`   | ✅ | Execute a BUY/SELL at the live price | 5 / 60s |

### Market Data
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/market/price/{pair}` | – | Live price from Redis (e.g. `BTC-USD`) |

### System
| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Health check |

> **Note:** `/market/price/{pair}` returns `503` until the gateway + worker have pushed at least one live price into Redis (usually a second or two after startup). Trade execution falls back to `$65,000` if no live price is cached yet.

---

## Environment variables

Defined in `.env` at the repo root. See [`.env.example`](.env.example).

| Variable | Used by | Notes |
|----------|---------|-------|
| `DATABASE_URL` | api | Async Postgres URL (`postgresql+asyncpg://...`) |
| `SECRET_KEY`   | api | Signs JWT tokens — change this for any real use |
| `REDIS_URL`    | api, worker | Inside Docker, host is `redis` |
| `RABBITMQ_URL` | worker, gateway | Inside Docker, host is `rabbitmq` |

> ⚠️ The committed defaults (`supersecretpassword`, `guest:guest`) are **for local demo only**. Never reuse them on a public server.

---

## Project layout

```
.
├── docker-compose.yml          # wires up all 6 services
├── execution-engine/           # Python / FastAPI
│   └── app/
│       ├── main.py             # app + router mounting + /health
│       ├── api/
│       │   ├── auth.py         # register / login
│       │   ├── trading.py      # portfolio / faucet / execute
│       │   ├── market.py       # live price
│       │   ├── deps.py         # JWT -> current user dependency
│       │   └── schemas.py      # Pydantic request/response models
│       ├── core/               # config, security, cache, rate_limit
│       ├── db/                 # models, session, base
│       └── worker.py           # RabbitMQ -> Redis consumer
│       └── migrations/         # Alembic database migrations
└── ingestion-gateway/          # Node / TypeScript
    └── src/index.ts            # Binance WS -> RabbitMQ publisher
```

---

## Tech stack

- **Python 3.12**, FastAPI, SQLAlchemy (async), Alembic, PyJWT, passlib/bcrypt
- **Node.js 22**, TypeScript, `ws`, `amqplib`
- **PostgreSQL**, **Redis**, **RabbitMQ**
- **Docker Compose** for orchestration
- **GitHub Actions** for CI

---

## Running services individually (optional)

If you'd rather not use Docker, see [`CLAUDE.md`](CLAUDE.md) for per-service local run commands (venv + uvicorn for Python, `npm run dev` for the gateway). You'll need Postgres, Redis, and RabbitMQ running locally.
