# 3x MVP

3x is a Python-first energy market intelligence MVP focused on power markets, starting with ERCOT. The backend owns ingestion, forecast generation, event extraction, event impact estimation, alerts, and API delivery; the Next.js frontend is a thin institutional dashboard over those services.

## Architecture Summary

- `backend/` contains the FastAPI app, SQLAlchemy models, pydantic schemas, synthetic seed generation, forecast pipeline, event intelligence logic, alert generation, and tests.
- `frontend/` contains the Next.js dashboard, market detail view, event intelligence page, and developer/API surface.
- `infrastructure/` contains Docker Compose for local startup with PostgreSQL and Redis.

The code is organized so ERCOT is the first launch market without hard-coding the platform to a single commodity forever. `Market` remains generic, event types are explicit and extensible, and the forecast layer uses a shared interface that can later support richer power or cross-commodity models.

## Product Scope

This MVP includes:

- Historical price, demand, and weather proxy ingestion via synthetic seed data
- A baseline probabilistic forecast service with confidence bands and spike probability
- Structured event extraction from seeded article-like inputs
- Heuristic event impact estimation
- Alert generation for spike risk and major grid events
- A frontend dashboard with forecast visualization, market detail, events, and developer notes

## Folder Structure

```text
backend/
  app/
    api/
    alerts/
    core/
    db/
    events/
    forecasting/
    ingestion/
    models/
    schemas/
    services/
  scripts/
  tests/
frontend/
  app/
  components/
  lib/
  types/
infrastructure/
```

## Local Setup

### Option 1: Python + Node locally

1. Copy `.env.example` to `.env` if you want to override defaults.
2. Install backend dependencies:

```bash
cd backend
python3 -m pip install -r requirements.txt
```

3. Start the API:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

4. Install frontend dependencies:

```bash
cd frontend
npm install
```

5. Start the frontend:

```bash
cd frontend
npm run dev
```

6. Open [http://localhost:3000](http://localhost:3000).

### Option 2: Docker Compose

```bash
cd infrastructure
docker compose up --build
```

This starts:

- Frontend on `http://localhost:3000`
- Backend API on `http://localhost:8000/api`
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`

## Key API Endpoints

- `GET /api/health`
- `GET /api/markets`
- `GET /api/markets/{market_id}`
- `GET /api/markets/{market_id}/prices`
- `GET /api/markets/{market_id}/forecast`
- `GET /api/markets/{market_id}/events`
- `GET /api/markets/{market_id}/alerts`
- `GET /api/events`
- `POST /api/articles/ingest`
- `POST /api/forecasts/run?market_code=ERCOT_NORTH`
- `GET /api/dashboard/ERCOT_NORTH`

## Forecasting Design

The initial forecast service is intentionally modest but credible:

- Feature engineering combines lagged prices, intraday seasonality, weather proxies, demand, renewable generation proxies, and event impact indicators.
- The default model is a scikit-learn gradient boosting regressor.
- Output includes point forecast, lower and upper bands, spike probability, and a short rationale summary.
- The model contract is upgrade-ready with `train()`, `predict()`, `predict_distribution()`, and `explain()`.

## Event Intelligence Design

The event pipeline follows a clean separation:

- `news_articles` store raw article-like objects.
- `events` store structured market-relevant signals.
- Extraction is currently rule-based with energy-specific keyword maps and lightweight heuristics.
- Impact estimation is heuristic and explicitly represented as an estimate, not false precision.

Supported MVP event types include generator outages, transmission outages, extreme weather alerts, renewable forecast revisions, and regulatory announcements.

## Tests

Run backend tests with:

```bash
cd backend
PYTHONPATH=. pytest
```

Coverage includes:

- schema validation
- event extraction logic
- forecast service behavior
- API response checks

## Demo Path

1. Open the dashboard and review the ERCOT North forecast.
2. Inspect the confidence band and spike probability.
3. Scroll the structured event feed to see how articles become market signals.
4. Open the market detail page to view historical prices and alerts.
5. Visit the developer page to confirm the API-first platform posture.

## Future Roadmap

- Replace synthetic data adapters with ERCOT and weather provider connectors
- Add richer event parsing and optional pluggable LLM extraction adapters
- Introduce authentication and saved alert preferences
- Expand market adapters to PJM, CAISO, natural gas, and carbon products
- Add model tracking, backtesting, and performance reporting
