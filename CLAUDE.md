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

## Kubernetes (k8s/) — Implementation Status

All manifests live in `k8s/`. The branch `feat/k8s-implementation` is active.
Apply order matters: namespace → configmap/secret → infra (postgres, redis, rabbitmq) → app (api, worker, gateway) → service → ingress.

### Done
| File | Resource | Notes |
|---|---|---|
| `deployment-api.yaml` | Deployment `aegis-api` | 2 replicas, httpGet `/health` probes, env from ConfigMap + Secret |
| `deployment-engine.yaml` | Deployment `aegis-worker` | 1 replica (exclusive AMQP queue — do not scale without changing worker.py), `command: ["python", "-m", "app.worker"]` overrides Dockerfile CMD, exec probe uses `find /tmp/worker_alive -newer /proc/1/cmdline` (worker.py touches file on every consumed message) |
| `deployment-redis.yaml` | Deployment `aegis-redis` + PVC | redis:7-alpine, AOF persistence (`--appendonly yes`), 1Gi PVC `aegis-redis-pvc`, `redis-cli ping` probes |
| `configmap.yaml` | ✅ Now includes `PAIRS` | `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,DOGEUSDT` — controls which Binance streams gateway subscribes to |

### All K8s files complete — verified working on minikube

All 12 manifests are implemented and the full stack has been verified running locally.
Every pod reached `1/1 Running`. `GET /health` returned `{"status": "Aegis execution engine is running"}`.

| File | Status | Notes |
|---|---|---|
| `namespace.yaml` | ✅ Done | Namespace `aegis`, label `app.kubernetes.io/part-of: aegis-trading` |
| `configmap.yaml` | ✅ Done | `REDIS_URL`, `RABBITMQ_URL`, `POSTGRES_DB`, `POSTGRES_USER` with K8s service hostnames |
| `secret.yaml` | ✅ Done (template) | `stringData` with `REPLACE_ME` placeholders. Gitignored once filled. |
| `statefulset-postgres.yaml` | ✅ Done | StatefulSet + headless Service + 5Gi PVC via `volumeClaimTemplates`, `subPath: postgres` |
| `deployment-redis.yaml` | ✅ Done | Deployment + 1Gi PVC, AOF persistence, `redis-cli ping` probes |
| `deployment-rabbitmq.yaml` | ✅ Done | Deployment, `rabbitmq-diagnostics` probes, credentials from Secret |
| `deployment-api.yaml` | ✅ Done | 2 replicas, httpGet `/health`, env from ConfigMap + Secret |
| `deployment-engine.yaml` | ✅ Done | 1 replica, `find /tmp/worker_alive` probe, heartbeat in worker.py |
| `deployment-gateway.yaml` | ✅ Done | 1 replica, httpGet port 3000 (health server added to index.ts) |
| `migrations-job.yaml` | ✅ Done | One-shot Job, `restartPolicy: OnFailure`, `backoffLimit: 4` |
| `service.yaml` | ✅ Done | ClusterIP for infra, LoadBalancer for API (port 80 → 8000) |
| `ingress.yaml` | ✅ Done | Optional nginx Ingress to `aegis.local`, alternative to LoadBalancer |

### Verified apply order (minikube)
```bash
minikube start --memory=4096 --cpus=2
eval $(minikube docker-env)
docker build -t aegis-execution-engine:latest ./execution-engine
docker build -t aegis-ingestion-gateway:latest ./ingestion-gateway

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/statefulset-postgres.yaml
kubectl apply -f k8s/service.yaml
kubectl wait --for=condition=ready pod/aegis-postgres-0 -n aegis --timeout=90s
kubectl apply -f k8s/migrations-job.yaml
kubectl wait --for=condition=complete job/aegis-migrations -n aegis --timeout=60s
kubectl apply -f k8s/deployment-redis.yaml
kubectl apply -f k8s/deployment-rabbitmq.yaml
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/deployment-engine.yaml
kubectl apply -f k8s/deployment-gateway.yaml

# In a second terminal:
minikube tunnel
# Then: kubectl get service aegis-api -n aegis → copy EXTERNAL-IP
# curl http://<EXTERNAL-IP>/health

# Teardown (preserve state):
minikube stop
# Teardown (full wipe):
kubectl delete namespace aegis && minikube stop
```

### Known startup behaviour
Worker and gateway restart 2–5 times on cold start — RabbitMQ takes ~25s to boot and they crash-loop until it is ready. This self-heals automatically via K8s backoff. `aegis-migrations` showing `Completed` is correct (Job, not a crash).

## Multi-pair trading (implemented)

Gateway now streams multiple Binance pairs via a single combined WebSocket connection.
Controlled by the `PAIRS` env var — no code changes needed to add new pairs.

### How it works
- `PAIRS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,DOGEUSDT` (set in `.env`, docker-compose, and `k8s/configmap.yaml`)
- Gateway builds Binance combined stream URL: `wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade/...`
- `symbolToPair()` in `index.ts` strips `USDT`/`BUSD`/`USD` suffix → `BTCUSDT` → `BTC-USD`
- Worker writes each pair's price to its own Redis key: `orderbook:BTC-USD:price`, `orderbook:ETH-USD:price`, etc.
- `POST /trading/execute` accepts any `pair` string — returns `503` if no live price exists for it (instead of the old silent `$65,000` fallback)

### To add a new pair
Add its Binance symbol to `PAIRS` in `.env` and restart the gateway. No code changes.

### Pairs that work out of the box
`BTC-USD`, `ETH-USD`, `SOL-USD`, `BNB-USD`, `DOGE-USD`

### Next feature — limit orders (`feat/limit-orders` branch)
`locked_balance` column exists on `portfolios` table (never written to yet).
It is reserved for limit order implementation:
- User places limit order → funds move `balance → locked_balance` (reserved, unavailable for other trades)
- Background poller checks Redis price → when price hits target → funds move `locked_balance → 0`, asset credited
- On cancel → `locked_balance → balance` (released)
Needs: `LimitOrder` table + migration, `POST /trading/limit-order`, `DELETE /trading/limit-order/{id}`, background polling task.

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) on push/PR to `main`:
1. Installs Node deps, compiles TypeScript
2. Installs Python deps
3. Verifies `docker compose build` for api, gateway, worker
4. On push to main only: SSH deploys to AWS EC2 via `docker compose up --build -d`

EC2 deployment requires GitHub secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`.
