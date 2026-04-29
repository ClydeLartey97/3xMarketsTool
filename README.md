# 3x Markets Tool

3x is a power-market intelligence MVP for monitoring wholesale electricity markets, forecasting near-term price risk, and translating market news into structured trading context. The product starts with ERCOT and now includes expansion coverage for PJM, NYISO, ISO-NE, Great Britain, EPEX Germany, EPEX France, and Nord Pool SE3.

The backend owns ingestion, feature engineering, forecasting, event extraction, risk scoring, alert generation, and API delivery. The Next.js frontend presents that data as an institutional market desk with market cards, charting, event intelligence, news evidence, and a position risk panel.

## What It Does

- Tracks configured power markets with seeded or live/fallback price, demand, weather, wind, and solar data.
- Builds probabilistic hourly forecasts with point estimates, confidence bands, spike probabilities, and model rationales.
- Ingests curated and RSS energy news, extracts market-relevant events, and estimates directional price impact.
- Scores position risk via `risk`, `likely`, and `upside` outputs using forecast distributions plus news/event context.
- Provides a Next.js dashboard, market workbench, event feed, API reference page, dark/light themes, and backend-offline states.

## Architecture

```text
backend/
  app/
    api/              FastAPI routes
    core/             settings and curated source metadata
    db/               SQLAlchemy engine/session setup
    events/           rule-based event extraction and impact heuristics
    forecasting/      feature builder and model interface/implementation
    ingestion/        real data, RSS, and seed population
    models/           SQLAlchemy ORM models
    schemas/          Pydantic response/request models
    services/         market, news, forecast, risk, alert service logic
  scripts/            local utility scripts
  tests/              backend pytest suite
frontend/
  app/                Next.js app routes
  components/         dashboard, charts, risk panel, shell, UI pieces
  lib/                API client
  types/              frontend domain types
infrastructure/       Docker Compose for Postgres, Redis, backend, frontend
```

## Requirements

- Python 3.12 recommended. The backend Dockerfile uses Python 3.12, and pinned data-science packages may not have wheels for newer Python versions.
- Node.js 20 or newer.
- npm.
- Optional: Docker and Docker Compose.
- Optional: EIA API key for richer U.S. grid data. The app degrades to computed/synthetic fallback data when unavailable.

## Local Quick Start

### 1. Backend

From the repository root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If you do not have Python 3.12 installed, `uv` is a convenient option:

```bash
python3 -m pip install --user uv
python3 -m uv venv /tmp/market-speculation-py312 --python 3.12
python3 -m uv pip install --python /tmp/market-speculation-py312/bin/python -r backend/requirements.txt
cd backend
/tmp/market-speculation-py312/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The first backend startup may take a little longer because it creates the database, seeds configured markets, tries public data sources, and falls back where needed.

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

## Environment

Copy `.env.example` to `.env` if you want to override defaults.

```env
DATABASE_URL=sqlite:///./threex.db
CORS_ORIGINS=["http://localhost:3000"]
API_INTERNAL_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

Useful optional variables:

- `EIA_API_KEY`: enables EIA U.S. grid demand and generation calls.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`: enables Gemini news-context scoring for the risk engine. Without it, the app uses deterministic heuristic scoring.
- `FORECAST_CACHE_TTL_MINUTES`: forecast cache TTL, default `15`.
- `DATA_REFRESH_INTERVAL_MINUTES`: background refresh interval, default `30`.

## Docker Compose

```bash
cd infrastructure
docker compose up --build
```

This starts:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/api`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

The frontend uses `API_INTERNAL_BASE_URL` for server-side container calls and `NEXT_PUBLIC_API_BASE_URL` for browser-side requests, so the browser should call `localhost` while the Next.js server can call the backend container hostname.

## Key API Endpoints

- `GET /api/health`
- `GET /api/markets`
- `GET /api/markets/{market_id}`
- `GET /api/markets/{market_id}/prices`
- `GET /api/markets/{market_id}/forecast`
- `GET /api/markets/{market_id}/events`
- `GET /api/markets/{market_id}/news`
- `GET /api/markets/{market_id}/alerts`
- `GET /api/events`
- `GET /api/news/sources`
- `GET /api/dashboard/{market_code}`
- `POST /api/articles/ingest`
- `POST /api/forecasts/run?market_code=ERCOT_NORTH`
- `POST /api/markets/{market_code}/refresh`
- `POST /api/risk-assessment`

Example risk request:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/risk-assessment \
  -H 'Content-Type: application/json' \
  -d '{
    "market_code": "ERCOT_NORTH",
    "position_gbp": 10000,
    "horizon_hours": 24,
    "direction": "long"
  }'
```

## Forecasting

The forecast service combines:

- lagged and rolling price features,
- intraday and day-of-week structure,
- weather, demand, wind, solar, and net-load features,
- event severity and estimated event impact,
- a gradient boosting regressor plus structural market anchors.

Responses include hourly forecasts, lower/upper bands, spike probability, model version, feature snapshots, and rationale summaries.

## Event And News Intelligence

The event pipeline stores raw `news_articles`, extracts structured `events`, and estimates price impact with explicit uncertainty. Current event types include:

- generator outage,
- transmission outage,
- extreme weather alert,
- renewable forecast revision,
- demand shock,
- regulatory or policy announcement.

RSS ingestion pulls recent articles from public energy sources and avoids duplicate source URLs. Seeded articles provide demo-ready market context even without external feeds.

## Risk Engine

`POST /api/risk-assessment` converts a market, position size, direction, and horizon into:

- `risk_gbp`: 95 percent CVaR-style downside estimate,
- `likely_gbp`: expected P&L,
- `upside_gbp`: 95th-percentile upside estimate,
- supporting volatility, confidence, regime, catalyst severity, asymmetry, and rationale fields.

The risk engine uses forecast bands, realized price volatility, recent events, and scored article context. If no LLM API key is configured, it uses a deterministic heuristic scorer.

## Frontend Pages

- `/`: market cards with latest spot, next-hour forecast, 24h average, and spike risk.
- `/markets/{marketCode}`: market workbench with charting, forecast band, drawing tools, signal stack, news briefs, model rationale, and risk panel.
- `/events`: all structured market events.
- `/developer`: API endpoint and platform notes.

## Validation

Backend syntax check:

```bash
python3 -m compileall -q backend/app backend/scripts backend/tests
```

Backend tests, in a Python 3.12 environment with dependencies installed:

```bash
cd backend
PYTHONPATH=. pytest
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
npm audit --audit-level=moderate
```

## Demo Flow

1. Open `/` and scan the market cards.
2. Open `ERCOT_NORTH` or another market card.
3. Use the chart controls and inspect the forecast band.
4. Adjust the position size, horizon, and direction in the risk panel.
5. Review news evidence and structured event catalysts.
6. Visit `/events` to inspect the broader event feed.
7. Visit `/developer` for endpoint details.

## Notes And Caveats

- This is an MVP and educational decision-support tool, not financial advice.
- Some market data is computed or synthetic when public APIs are unavailable or unauthenticated.
- The local SQLite database is created under `backend/threex.db` by default and is ignored by git.
- The frontend has both server-side and browser-side API calls, so keep `API_INTERNAL_BASE_URL` and `NEXT_PUBLIC_API_BASE_URL` distinct when running in containers.

## Roadmap

- Add richer market-specific adapters and backfills.
- Add migrations instead of relying on `metadata.create_all` for schema setup.
- Add authentication and saved user watchlists.
- Add model backtesting and forecast performance reporting.
- Expand event extraction beyond rule-based heuristics.
- Add CI for backend tests, frontend build, lint, and audit.
