# 3x Markets Tool

3x is a power-market intelligence MVP for monitoring wholesale electricity markets, forecasting near-term price risk, and translating market news into structured trading context. The product starts with ERCOT and now includes expansion coverage for PJM, NYISO, ISO-NE, Great Britain, EPEX Germany, EPEX France, and Nord Pool SE3.

The backend owns ingestion, feature engineering, forecasting, event extraction, risk scoring, alert generation, and API delivery. The Next.js frontend presents that data as an institutional market desk with market cards, charting, event intelligence, news evidence, and a position risk panel.

## What It Does

- Tracks configured power markets with seeded, live, and backfilled price, demand, weather, wind, and solar data — every market now carries 2 years of hourly history.
- Builds probabilistic hourly forecasts with point estimates, confidence bands, spike probabilities, and model rationales. The forecast is **walk-forward backtested** against persistence, persistence-24h, and climatology baselines, with PIT calibration.
- Ingests curated and RSS energy news, extracts market-relevant events, and estimates directional price impact.
- Scores position risk via `risk`, `likely`, and `upside` outputs using Monte Carlo price paths, forecast distributions, FX conversion, and news/event context.
- Exposes a **transparent coefficient breakdown** for every risk number — every parameter that drives `risk_gbp / likely_gbp / upside_gbp` is surfaced in the API response and rendered in a Bloomberg-style decomposition table on the dashboard.
- Provides a Next.js dashboard with a live multi-market ticker strip, market workbench, event feed, API reference page, dark/light themes, and backend-offline states.
- Surfaces data provenance so users can see what share of the recent chart is real versus synthetic/computed.

## Architecture

```text
backend/
  app/
    api/              FastAPI routes
    core/             settings and curated source metadata
    db/               SQLAlchemy engine/session setup
    events/           rule-based event extraction and impact heuristics
    forecasting/      feature builder, model, and walk-forward backtest framework
    ingestion/        real data, backfills, RSS, and seed population
    models/           SQLAlchemy ORM models
    schemas/          Pydantic response/request models
    services/         market, news, forecast, risk simulator, FX, alert services
  scripts/            local utility scripts (seed, backfill, backtest)
  reports/            JSON output from the backtest runner
  tests/              backend pytest suite
frontend/
  app/                Next.js app routes
  components/         dashboard, charts, risk panel, shell, UI pieces
  lib/                API client
  types/              frontend domain types
infrastructure/       Docker Compose for Postgres, Redis, backend, frontend
```

## Requirements

- Python 3.14 is tested locally for the backend suite. Python 3.12 remains compatible with the backend Dockerfile.
- Node.js 20 or newer.
- npm.
- Optional: Docker and Docker Compose.
- Optional but recommended: EIA API key for real U.S. grid demand and generation history. Without it, U.S. markets can still show computed chart continuity but are flagged as degraded.

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
- `ACTIVE_FORECASTER`: forecast backend, default `gbr`. Supported values are `gbr`, `chronos`, and `naive_persistence_24h`.
- `CHRONOS_DEVICE_MAP`: Chronos-Bolt inference device, default `cpu`. Use `cuda` on GPU hosts or `mps` on Apple Silicon when available.
- `CHRONOS_USE_SMALL`: when `true`, uses `amazon/chronos-bolt-small`; otherwise Chronos uses the lighter `amazon/chronos-bolt-tiny`.
- `DATA_REFRESH_INTERVAL_MINUTES`: background refresh interval, default `30`.
- `DEMO_MODE`: when `true`, permits computed/synthetic fallback data without marking the market degraded. Defaults to `false`.

## Domain News Scorer Training

Phase D adds a LoRA training path for the structured news scorer. The runtime
backend dependencies stay lean; training dependencies live in
`backend/requirements-train.txt`.

GPU expectation: use a CUDA host with roughly 24GB VRAM for
`meta-llama/Llama-3.1-8B-Instruct`. If that model is gated for your Hugging Face
account, use `--model-id Qwen/Qwen2.5-7B-Instruct`.

```bash
cd backend
python -m pip install -r requirements.txt
python -m pip install -r requirements-train.txt
PYTHONPATH=. python3 scripts/build_news_dataset.py --target-rows 5000
PYTHONPATH=. python3 scripts/finetune_news_scorer.py --dry-run
PYTHONPATH=. python3 scripts/finetune_news_scorer.py --model-id meta-llama/Llama-3.1-8B-Instruct
```

The dry run validates prompt formatting and writes
`backend/models/news_scorer_lora/training_manifest.json`. A real run writes the
LoRA adapter files into the same directory.

## Historical Backfill

Phase 3 adds a rerunnable historical backfill path. It keeps the existing hourly timestamp dedupe, so it is safe to run more than once.

```bash
cd backend
PYTHONPATH=. python3 scripts/backfill.py --lookback-days 730 --market GB_POWER
PYTHONPATH=. EIA_API_KEY=your_key_here python3 scripts/backfill.py --lookback-days 365 --market ERCOT_NORTH
```

If no `--market` is provided, the script runs every configured market.

Current adapters:

- `GB_POWER`: ELEXON BMRS Market Index Data in 7-day windows.
- U.S. markets: EIA hourly demand/generation in monthly windows when `EIA_API_KEY` is set.
- All markets: Open-Meteo archive weather for long historical ranges.

Backfilled U.S. markets without an EIA key are still chartable, but their prices are computed from fundamentals and the API marks the market `data_status="degraded"`.

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
- `GET /api/markets/{market_id}/prices?limit=720`
- `GET /api/markets/{market_id}/history?from=2025-04-30T00:00:00Z&to=2026-04-30T00:00:00Z`
- `GET /api/markets/{market_id}/forecast`
- `GET /api/markets/{market_id}/events`
- `GET /api/markets/{market_id}/news`
- `GET /api/markets/{market_id}/alerts`
- `GET /api/events`
- `GET /api/news/sources`
- `GET /api/dashboard/{market_code}?history_hours=720`
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

Set `ACTIVE_FORECASTER=chronos` to use Chronos-Bolt zero-shot forecasts. CPU inference works with the tiny model for local development; GPU is optional but recommended for lower latency or when enabling `CHRONOS_USE_SMALL=true`.

Responses include hourly forecasts, lower/upper bands, spike probability, model version, feature snapshots, and rationale summaries.

## Data Provenance

Dashboard responses include:

- `key_metrics.data_freshness_minutes`: age of the newest price point in minutes.
- `key_metrics.synthetic_share_24h`: fraction of the last 24 hours using computed or synthetic price sources.
- `market.data_status`: `ready` or `degraded`.

The dashboard displays a "Data: X% real / Y% synthetic" strip. When `data_status="degraded"`, the risk panel hides the headline risk numbers and asks the user to refresh or backfill real data instead of presenting synthetic-driven risk as if it were market-grade.

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

- `risk_gbp`: 95 percent empirical CVaR downside estimate,
- `likely_gbp`: expected P&L,
- `upside_gbp`: 95th-percentile upside estimate,
- path-dependent fields such as probability of loss and max drawdown,
- supporting volatility, confidence, regime, catalyst severity, asymmetry, FX, and rationale fields.

The risk engine uses Monte Carlo simulation, forecast-implied volatility, realized price volatility, recent events, native market currencies, FX conversion to GBP, and scored article context. If no LLM API key is configured, it uses a deterministic heuristic scorer.

### Coefficient transparency

Every parameter that flows into the three headline numbers is exposed in the response under `coefficients.items`, grouped into:

- `forecast`: spot, forecast point, model σ, MAE, directional accuracy.
- `realised_vol`: hourly σ, sample size, realised-vs-model blend weight, blended σ at horizon.
- `llm`: tail multiplier, asymmetry, catalyst severity, asymmetry-driven drift, total drift, regime, LLM confidence, CVaR multiplier.
- `fx`: native price currency and the conversion rate to GBP.
- `position`: GBP notional, native notional, hedge ratio, direction sign, horizon, Monte Carlo path count.
- `result`: σ used, expected return, P(loss), edge score, max drawdown.

Each item carries a `label`, numeric `value`, `unit`, and one-line `description`. The dashboard renders the block as a Bloomberg-style grouped table, alongside the equation summary that ties them together.

### Backtesting

`backend/scripts/backtest.py` runs a walk-forward backtest over real market history and writes a JSON report to `backend/reports/`. It scores the forecaster's MAE / RMSE / directional accuracy / spike F1 against three baselines (persistence, persistence-24h, climatology), produces an hour-of-day and regime breakdown, and computes a PIT calibration histogram.

```bash
cd backend
PYTHONPATH=. python3 scripts/backtest.py --market GB_POWER --lookback-days 365
```

The checked-in GB_POWER report at `backend/reports/backtest_GB_POWER_20260507_2112.json` covers a 365-day lookback with 49,896 forecasted hourly samples. It shows:

- model RMSE: `21.79` £/MWh,
- persistence-24h RMSE: `33.76` £/MWh,
- climatology RMSE: `48.72` £/MWh,
- 1-hour persistence RMSE: `12.69` £/MWh,
- PIT max deviation from uniform: `0.2881`, so intervals are still too narrow.

That means the current forecaster beats the day-ahead and climatology baselines, but not the simplest 1-hour persistence baseline yet. Treat the report as a useful Phase 4 diagnostic, not a claim that calibration is solved.

## Frontend Pages

- `/`: live multi-market ticker, market cards, range-selectable history chart, latest forecast, data-quality strip, and event context.
- `/markets/{marketCode}`: market workbench with charting, forecast band, drawing tools, signal stack, news briefs, model rationale, risk panel, and risk decomposition table.
- `/events`: all structured market events.
- `/developer`: API endpoint and platform notes.

## Validation

Backend syntax check:

```bash
python3 -m compileall -q backend/app backend/scripts backend/tests
```

Backend tests, in a Python environment with dependencies installed:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/
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
3. Use the dashboard history controls: `1D`, `1W`, `1M`, `1Y`, `2Y`, or `Max`.
4. Adjust the position size, horizon, and direction in the risk panel.
5. Review news evidence and structured event catalysts.
6. Visit `/events` to inspect the broader event feed.
7. Visit `/developer` for endpoint details.

## Notes And Caveats

- This is an MVP and educational decision-support tool, not financial advice.
- Some market data is computed or synthetic when public APIs are unavailable or unauthenticated. The UI now labels this explicitly.
- U.S. real historical data requires `EIA_API_KEY`; otherwise U.S. markets are marked degraded outside demo mode.
- The local SQLite database is created under `backend/threex.db` by default and is ignored by git.
- The frontend has both server-side and browser-side API calls, so keep `API_INTERNAL_BASE_URL` and `NEXT_PUBLIC_API_BASE_URL` distinct when running in containers.

## Roadmap

- Surface the latest backtest report on the dashboard (model RMSE vs persistence-24h, PIT calibration, hour-of-day breakdown) and run the backtest nightly.
- Regime-conditional residual σ so the predictive intervals are calibrated (current PIT histogram on GB_POWER is too narrow).
- Migrate charting from Recharts to KLineCharts with built-in drawing tools, plus demand / wind / solar overlays and event markers.
- Replace the rule-based event extractor with an LLM classifier and add a structured event schema (zone, magnitude, duration distribution, historical analogues).
- Add Postgres + Alembic migrations, background workers (arq/rq) and Redis-backed caches in place of in-process state.
- Add authentication, per-user watchlists, position blotter, and rate limiting.
- Add CI for backend tests, frontend build, lint, and audit.
