# Aegis Trading Engine

An event-driven crypto trading backend that streams **live crypto prices** from Binance across multiple pairs (BTC, ETH, SOL, BNB, DOGE — configurable), lets users register, fund a test wallet, and execute server-authoritative trades against live market prices.

Built as a portfolio / interview demo to showcase async Python, message-driven architecture, containerized microservices, and Kubernetes deployment.

---

## Table of Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Quick start — Docker Compose](#quick-start--docker-compose)
- [Running on Kubernetes (minikube)](#running-on-kubernetes-minikube)
- [Exploring the API](#exploring-the-api)
- [API reference](#api-reference)
- [Environment variables](#environment-variables)
- [Project layout](#project-layout)
- [Tech stack](#tech-stack)

---

## What it does

```
Binance combined stream (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT — configurable)
        │  (single WebSocket wss://stream.binance.com/stream?streams=...)
        ▼
 ingestion-gateway (Node/TS) ──publishes each pair──► RabbitMQ fanout exchange "market-data"
                                                              │
                                                              ▼
                                                execution-engine worker (Python)
                                                              │  writes to Redis per pair:
                                                              │  orderbook:BTC-USD:price
                                                              │  orderbook:ETH-USD:price  ...
                                                              ▼
                                                            Redis
                                                              │  read on every trade request
                                                              ▼
                                          FastAPI REST API  /api/v1/...
```

**Supported pairs** are controlled by the `PAIRS` env var (default: `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,DOGEUSDT`). The gateway opens one Binance combined stream for all configured pairs — add any valid Binance USDT symbol to `PAIRS` and restart the gateway, no code changes needed. Requesting a pair not in `PAIRS` returns `503` — there is no silent fallback price.

The trade price is **always taken from Redis on the server**, never from the client request — so a user cannot spoof a favourable price.

---

## Architecture

Six services wired together:

| Service | Tech | Role |
|---|---|---|
| `gateway` | Node.js / TypeScript | Connects to Binance combined stream, publishes live prices for all configured pairs to RabbitMQ |
| `rabbitmq` | RabbitMQ 3 | Fanout message bus. Management UI on `:15672` |
| `worker` | Python (aio-pika) | Consumes RabbitMQ → writes live price to Redis |
| `redis` | Redis 7 | Price cache + per-user rate-limit counters |
| `api` | Python / FastAPI | REST API: auth, portfolio, trading, market price |
| `postgres` | PostgreSQL 15 | Users, portfolios, transaction ledger |

### Key design decisions

**Server-authoritative pricing** — `POST /trading/execute` fetches the price from Redis inside the transaction, never from the request body. If Redis has no price yet, it falls back to `$65,000` so the API stays usable before the gateway connects.

**Atomic trade execution** — balance fetch → debit/credit → transaction record → single `db.commit()`, with explicit `db.rollback()` on any error. No partial state is ever written.

**Exclusive AMQP queue** — the worker declares an unnamed exclusive queue. Each worker replica gets its own copy of every price message (fanout semantics). Scaling the worker beyond 1 replica multiplies Redis writes, it does not distribute load. To enable horizontal scaling the queue would need to be named and non-exclusive.

**`locked_balance` column** — present on the `portfolios` table but not written to by any current endpoint. It is a schema stub reserved for future limit-order functionality.

---

## Quick start — Docker Compose

> You only need **Docker Desktop** installed.

### 1. Create your `.env`

```bash
cp .env.example .env
```

### 2. Launch everything

```bash
docker compose up --build
```

Wait until the API and gateway logs settle (~15 seconds). All six services are now running.

### 3. Open the interactive docs

**http://localhost:8000/docs** — Swagger UI with every endpoint. See the [walkthrough](#exploring-the-api) below.

### 4. Shut down

```bash
docker compose down        # stop containers, keep volumes
docker compose down -v     # stop and wipe the postgres + redis volumes
```

---

## Running on Kubernetes (minikube)

The `k8s/` directory contains fully implemented manifests for the entire stack.

### Prerequisites

- [minikube](https://minikube.sigs.k8s.io/docs/start/) v1.32+
- [kubectl](https://kubernetes.io/docs/tasks/tools/) configured
- Docker Desktop

### 1. Start minikube and point Docker at it

```bash
minikube start --memory=4096 --cpus=2

# Point your shell at minikube's Docker daemon so locally-built images
# are available inside the cluster without pushing to a registry:
eval $(minikube docker-env)
```

### 2. Build images inside minikube

```bash
docker build -t aegis-execution-engine:latest ./execution-engine
docker build -t aegis-ingestion-gateway:latest ./ingestion-gateway
```

Both manifests already have `imagePullPolicy: Never` set.

### 3. Fill in secrets

Edit `k8s/secret.yaml` — replace the placeholders with real values:

```yaml
stringData:
  DATABASE_URL: "postgresql+asyncpg://aegis_admin:<password>@aegis-postgres:5432/aegis_db"
  SECRET_KEY: "<your-jwt-secret>"
  POSTGRES_PASSWORD: "<password>"
  RABBITMQ_DEFAULT_USER: "guest"
  RABBITMQ_DEFAULT_PASS: "guest"
```

> `k8s/secret.yaml` is in `.gitignore` — it will not be committed once you fill in real values.

### 4. Apply manifests in order

```bash
# Foundation
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# Postgres must be ready before migrations run
kubectl apply -f k8s/statefulset-postgres.yaml
kubectl apply -f k8s/service.yaml
kubectl wait --for=condition=ready pod/aegis-postgres-0 -n aegis --timeout=90s

# Run database migrations once as a Job
kubectl apply -f k8s/migrations-job.yaml
kubectl wait --for=condition=complete job/aegis-migrations -n aegis --timeout=60s

# Remaining infra
kubectl apply -f k8s/deployment-redis.yaml
kubectl apply -f k8s/deployment-rabbitmq.yaml

# Application layer
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/deployment-engine.yaml
kubectl apply -f k8s/deployment-gateway.yaml
```

### 5. Watch pods come up

```bash
kubectl get pods -n aegis --watch
```

Expected final state:

```
NAME                              READY   STATUS      RESTARTS
aegis-api-xxx                     1/1     Running     0          ← 2 replicas
aegis-api-xxx                     1/1     Running     0
aegis-worker-xxx                  1/1     Running     0-5        ← restarts during RabbitMQ cold boot are normal
aegis-gateway-xxx                 1/1     Running     0-2
aegis-postgres-0                  1/1     Running     0
aegis-rabbitmq-xxx                1/1     Running     0
aegis-redis-xxx                   1/1     Running     0
aegis-migrations-xxx              0/1     Completed   0          ← Job, Completed is correct
```

The worker and gateway may restart a few times during initial startup — RabbitMQ takes ~25 seconds to boot and they crash-loop until it is ready. This self-heals automatically.

### 6. Access the API

In a **separate terminal**, keep this running (needs sudo for port binding):

```bash
minikube tunnel
```

Then:

```bash
kubectl get service aegis-api -n aegis   # copy EXTERNAL-IP
curl http://<EXTERNAL-IP>/health
# open http://<EXTERNAL-IP>/docs for Swagger UI
```

### 7. Debug RabbitMQ management UI (optional)

```bash
kubectl port-forward -n aegis service/aegis-rabbitmq 15672:15672
# open http://localhost:15672  (login: guest / guest)
```

### 8. Tear down

```bash
minikube stop                   # suspend VM, all data preserved for next session
# or full wipe:
kubectl delete namespace aegis  # removes all objects including PVCs
minikube stop
```

---

## Exploring the API

Open **http://localhost:8000/docs** (Docker) or **http://\<EXTERNAL-IP\>/docs** (minikube):

1. **`POST /api/v1/auth/register`** — create an account with email + password
2. **`POST /api/v1/auth/login`** — get a JWT. Copy the `access_token`
3. Click **Authorize** (top right) and paste the token
4. **`POST /api/v1/trading/faucet`** — fund your account with $100,000 fake USD (rate limited: once per 60 seconds)
5. **`GET /api/v1/market/price/BTC-USD`** — see the live BTC/USD price from Binance
6. **`POST /api/v1/trading/execute`** — buy BTC at the live price:
   ```json
   { "type": "BUY", "pair": "BTC-USD", "amount": 0.1 }
   ```
7. **`GET /api/v1/trading/portfolio`** — verify your USD decreased and BTC increased
8. **`POST /api/v1/trading/execute`** — sell it back:
   ```json
   { "type": "SELL", "pair": "BTC-USD", "amount": 0.1 }
   ```

`GET /health` requires no auth and is used by K8s liveness/readiness probes.

---

## API reference

Base path: `/api/v1`

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | — | Register with `email` + `password`. Returns user object |
| `POST` | `/auth/login` | — | Returns JWT (`access_token`). Token is valid for 7 days |

### Trading & Portfolio

| Method | Path | Auth | Description | Rate limit |
|---|---|---|---|---|
| `GET` | `/trading/portfolio` | ✅ JWT | Returns all asset balances for the current user | — |
| `POST` | `/trading/faucet` | ✅ JWT | Credits $100,000 USD to your account (dev/demo only) | 1 req / 60s per user |
| `POST` | `/trading/execute` | ✅ JWT | Execute a `BUY` or `SELL` at the live server-side price | 5 req / 60s per user |

`/trading/execute` request body:

```json
{ "type": "BUY", "pair": "BTC-USD", "amount": 0.5 }
```

- `type`: `"BUY"` or `"SELL"`
- `pair`: only `"BTC-USD"` has a live price. Any other value uses a fallback of `$65,000`
- `amount`: quantity of the base asset (BTC). Stored as `Decimal(18,8)`

### Market Data

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/market/price/{pair}` | — | Live price from Redis. Returns `503` if no price is cached yet |

### System

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "Aegis execution engine is running"}` |

---

## Environment variables

| Variable | Used by | Docker Compose value | K8s value |
|---|---|---|---|
| `DATABASE_URL` | api | `...@postgres:5432/...` | `...@aegis-postgres:5432/...` |
| `SECRET_KEY` | api | `super-secret` | from `k8s/secret.yaml` |
| `REDIS_URL` | api, worker | `redis://redis:6379/0` | `redis://aegis-redis:6379/0` |
| `RABBITMQ_URL` | worker, gateway | `amqp://guest:guest@rabbitmq:5672/` | `amqp://guest:guest@aegis-rabbitmq:5672/` |
| `PAIRS` | gateway | `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,DOGEUSDT` | from `k8s/configmap.yaml` |

The hostnames differ between Docker Compose (container names) and K8s (Service names). See `k8s/configmap.yaml` and `k8s/secret.yaml`.

To add a new tradeable pair, append its Binance USDT symbol to `PAIRS` and restart the gateway. The pair becomes available as `BASE-USD` in the API (e.g. `AVAXUSDT` → `AVAX-USD`).

> The committed defaults are **for local demo only**. Do not reuse them on a public server.

---

## Project layout

```
.
├── docker-compose.yml               # wires all 6 services for local dev
├── .env.example                     # copy to .env before running
├── execution-engine/                # Python / FastAPI service
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                  # FastAPI app, router mounting, /health
│       ├── worker.py                # RabbitMQ consumer → Redis writer
│       ├── api/
│       │   ├── auth.py              # POST /auth/register, /auth/login
│       │   ├── trading.py           # GET /portfolio, POST /faucet, POST /execute
│       │   ├── market.py            # GET /market/price/{pair}
│       │   ├── deps.py              # JWT → current user FastAPI dependency
│       │   └── schemas.py           # Pydantic request/response models
│       ├── core/
│       │   ├── config.py            # Settings (SECRET_KEY, JWT expiry: 7 days)
│       │   ├── security.py          # bcrypt_sha256 hashing, JWT creation
│       │   ├── cache.py             # Redis async client
│       │   └── rate_limit.py        # Redis INCR+EXPIRE rate limiter
│       └── db/
│           ├── models.py            # User, Portfolio, Transaction (UUID PKs, Decimal(18,8))
│           ├── session.py           # SQLAlchemy async engine + session
│           └── base.py              # declarative Base
│   └── migrations/                  # Alembic migration versions
├── ingestion-gateway/               # Node.js / TypeScript service
│   ├── Dockerfile
│   ├── package.json
│   └── src/index.ts                 # Binance WS → RabbitMQ publisher + HTTP health server (port 3000)
└── k8s/                             # Kubernetes manifests (fully implemented)
    ├── namespace.yaml               # Namespace: aegis
    ├── configmap.yaml               # Non-secret env vars (service DNS names)
    ├── secret.yaml                  # Credentials (gitignored when filled with real values)
    ├── statefulset-postgres.yaml    # Postgres StatefulSet + headless Service + 5Gi PVC
    ├── deployment-redis.yaml        # Redis Deployment + 1Gi PVC (AOF persistence)
    ├── deployment-rabbitmq.yaml     # RabbitMQ Deployment
    ├── deployment-api.yaml          # FastAPI Deployment (2 replicas)
    ├── deployment-engine.yaml       # Worker Deployment (1 replica — see scaling note above)
    ├── deployment-gateway.yaml      # Gateway Deployment (1 replica)
    ├── migrations-job.yaml          # One-shot Alembic migration Job (run before api Deployment)
    ├── service.yaml                 # ClusterIP services for infra + LoadBalancer for API
    └── ingress.yaml                 # Optional nginx Ingress (alternative to LoadBalancer)
```

---

## Tech stack

- **Python 3.12** — FastAPI, SQLAlchemy 2 (async), Alembic, PyJWT, passlib (bcrypt_sha256), aio-pika, redis-py
- **Node.js 22** — TypeScript, `ws`, `amqplib`
- **PostgreSQL 15** — primary datastore (users, portfolios, transactions)
- **Redis 7** — live price cache + rate-limit counters
- **RabbitMQ 3** — fanout message bus between gateway and worker
- **Docker Compose** — local development orchestration
- **Kubernetes** — production-grade deployment manifests (`k8s/`), verified on minikube
- **GitHub Actions** — CI: TypeScript compile, Python dependency install, Docker build verification
