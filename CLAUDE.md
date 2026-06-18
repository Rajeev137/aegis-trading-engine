# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Aegis is an event-driven trading backend composed of two services:
- **execution-engine** — Python/FastAPI REST API + async background worker
- **ingestion-gateway** — Node.js/TypeScript service that streams live BTC prices from Binance WebSocket to RabbitMQ

Data flow: `Binance WS → ingestion-gateway → RabbitMQ (fanout exchange "market-data") → execution-engine worker → Redis → FastAPI /market endpoint`

## Environment Setup

Both services require a `.env` file at the repo root with:
```
DATABASE_URL=postgresql+asyncpg://aegis_admin:supersecretpassword@localhost:5432/aegis_db
SECRET_KEY=your_secret_key_here
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

## Common Commands

### Run everything (recommended)
```bash
docker compose up --build
```
Services: postgres (5432), redis (6379), rabbitmq (5672 + mgmt UI 15672), api (8000), worker, gateway.

### execution-engine (Python)

```bash
cd execution-engine
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run API locally (requires postgres + redis + rabbitmq running)
uvicorn app.main:app --reload

# Run background worker locally
python -m app.worker

# Database migrations
alembic upgrade head          # apply all migrations
alembic revision --autogenerate -m "description"  # generate new migration
alembic downgrade -1          # roll back one step
```

Alembic reads `DATABASE_URL` from the environment; `migrations/env.py` sets `target_metadata = Base.metadata` so it auto-detects model changes.

### ingestion-gateway (Node.js/TypeScript)

```bash
cd ingestion-gateway
npm ci

npm run dev      # run with tsx (no compile step)
npm run build    # compile TypeScript → dist/
npm start        # run compiled dist/index.js
```

## Architecture Notes

### execution-engine structure
- `app/main.py` — FastAPI app, mounts three routers under `/api/v1/`
- `app/api/auth.py` — `/auth/register` and `/auth/login` (returns JWT)
- `app/api/trading.py` — `/trading/portfolio`, `/trading/faucet` (dev funding), `/trading/execute`
- `app/api/market.py` — `/market/price` reads live price from Redis key `orderbook:{pair}:price`
- `app/api/deps.py` — `get_current_user` dependency: decodes JWT Bearer token, fetches User from DB
- `app/core/security.py` — bcrypt hashing via passlib, JWT creation via PyJWT
- `app/core/rate_limit.py` — Redis-backed rate limiter (incr + expire pattern); faucet: 1/60s, execute: 5/60s
- `app/db/models.py` — `User`, `Portfolio`, `Transaction` (UUID PKs, `Numeric(18,8)` for balances)
- `app/worker.py` — consumes RabbitMQ fanout, writes `orderbook:{pair}:price` to Redis

### Key patterns
- All DB access uses SQLAlchemy async (`AsyncSession`); never use sync ORM methods
- Trade execution in `trading.py` is fully atomic: fetch balances → update → record `Transaction` → single `db.commit()`, with explicit `db.rollback()` on `ValueError` or exceptions
- `Portfolio` has a `UniqueConstraint('user_id', 'asset_symbol')` — wallets are auto-created on first trade if missing
- The price used in trades is always fetched from Redis (server-authoritative), not from the client request; falls back to `$65000.00` if Redis has no price yet

### ingestion-gateway
- Single file: `src/index.ts`
- Connects to Binance `btcusdt@trade` stream, extracts `trade.p` (price), publishes `{ pair: 'BTC-USD', price }` JSON to RabbitMQ fanout exchange `market-data`
- Currently hardcoded to BTC/USD only

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) on push/PR to `main`:
1. Installs Node deps, compiles TypeScript
2. Installs Python deps
3. Verifies `docker compose build` for api, gateway, worker
4. On push to main only: SSH deploys to AWS EC2 via `docker compose up --build -d`

EC2 deployment requires GitHub secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`.
