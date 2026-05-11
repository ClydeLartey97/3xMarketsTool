<div align="center">

<img src="assets/logo.svg" alt="3x Intelligent Markets" width="540"/>

*Glass-box power-market risk analytics. Nine markets, three currencies, two years of hourly history.*

[Features](#what-it-does) · [Quick start](#local-quick-start) · [Risk engine](#risk-engine) · [API](#key-api-endpoints) · [Roadmap](FRONTIER.md)

</div>

---

3x is power-market intelligence software for monitoring wholesale electricity markets, forecasting near-term price risk, and translating market news into structured trading context. It covers ERCOT (North + Houston), PJM Western Hub, NYISO Zone J, ISO-NE Mass Hub, Great Britain, EPEX Germany, EPEX France, and Nord Pool SE3.

The backend owns ingestion, feature engineering, forecasting, event extraction, risk scoring, alert generation, and API delivery. The Next.js frontend is a Bloomberg-style trading desk with a live multi-market ticker, range-selectable charting, structured news + events, and a transparent risk-decomposition workspace.

## What It Does

- **Two years of hourly history per market** — real ELEXON spot prices for GB; real EIA demand + Open-Meteo archive weather for US markets; computed-from-fundamentals fallback elsewhere. Data provenance is surfaced on every dashboard.
- **Probabilistic hourly forecasts** with point estimates, confidence bands, spike probabilities, and rationales. Walk-forward backtested against persistence, persistence-24h, and climatology baselines, with PIT calibration. Pluggable forecaster registry supports gradient boosting (default), Chronos-Bolt foundation model, and naive baselines.
- **Monte Carlo risk engine** producing `risk_gbp / likely_gbp / upside_gbp` from 5,000+ simulated price paths. Native-currency pricing with FX conversion to GBP at the boundary. Tail-aware CVaR (Gaussian → Student-t(5) blend), regime-conditional residual σ, and LLM-conditioned drift/tail adjustments.
- **Glass-box decomposition** — every parameter that drives the three numbers is surfaced in the API response (`coefficients.items`) and rendered as a Bloomberg-style grouped table in the UI. No black-box outputs.
- **Position-sizing solver, sensitivity ladder, calibration badge, decision diary, path-fan visualisation** — five UX modes that make the three numbers the centre of the workflow rather than a readout.
- **Portfolio risk** with joint Monte Carlo across positions using the cross-market correlation matrix. Optimal hedge ratios suggested by a trained deep-hedging policy.
- **Cross-zone basis trades** — paired correlated MC between two markets, returns spread P&L on the combined position.
- **DC optimal power flow** on a canonical 13-bus / 13-line grid topology covering every priced market. LMPs, line flows, and binding-line detection visible at `/grid`. Congestion-aware σ overlay tightens risk when transmission is stressed.
- **Structured event schema** with zone, magnitude_mw, duration distributions (p10/p50/p90), and historical analogue matching.
- **News intelligence pipeline** with RSS ingestion, heuristic / Gemini / domain-LoRA scorers (configurable), and event extraction.

## Architecture

```text
backend/
  app/
    api/              FastAPI routes
    core/             settings and curated source metadata
    db/               SQLAlchemy engine/session setup + SQLite compatibility shim
    events/           event extraction (heuristic) and impact heuristics
    forecasting/      feature builder, model registry, regime classifier,
                      walk-forward backtest framework, Chronos-Bolt adapter
    grid/             DC-OPF solver, topology loader, congestion overlay
    ingestion/        real-data adapters, backfills, RSS, seed population
    models/           SQLAlchemy ORM models
    schemas/          Pydantic request/response models
    services/         market, news, forecast, risk simulator, FX,
                      correlation, deep hedger, calibration, decisions,
                      event analogues, risk ablation
  data/               grid topology JSON, news training corpus
  models/             deep-hedger weights, LoRA adapter directory
  scripts/            seed, backfill, backtest, risk ablation, topology
                      ingest, deep-hedger training, LoRA fine-tune
  reports/            JSON / HTML output from the backtest and ablation runners
  tests/              backend pytest suite
frontend/
  app/                Next.js app routes (dashboard, market workbench,
                      events, developer, grid)
  components/         risk panel, decomposition, sensitivity ladder,
                      path-fan, calibration badge, decision diary,
                      position blotter, KLineCharts chart, grid topology view,
                      markets ticker, news / events feeds
  lib/                API client, market-history hook, typography tokens
  types/              frontend domain types
infrastructure/       Docker Compose for Postgres, Redis, backend, frontend
```

See `PLAN.md` for the original phase-by-phase upgrade specification and `FRONTIER.md` for the live 6-phase frontier roadmap (Phases A–E complete, Phase F enterprise hardening pending).

## Requirements

- Python 3.14 is tested locally for the backend suite. Python 3.12 remains compatible with the backend Dockerfile.
- Node.js 20 or newer.
- npm.
- Optional: Docker and Docker Compose.
- Optional but recommended: EIA API key for real U.S. grid demand and generation history. Without it, U.S. markets fall back to computed prices and the market is marked degraded.

## Local Quick Start

### 1. Backend

From the repository root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd ..
alembic -c alembic.ini upgrade head
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If you do not have Python 3.12 installed, `uv` is a convenient option:

```bash
python3 -m pip install --user uv
python3 -m uv venv /tmp/market-speculation-py312 --python 3.12
python3 -m uv pip install --python /tmp/market-speculation-py312/bin/python -r backend/requirements.txt
/tmp/market-speculation-py312/bin/python -m alembic -c alembic.ini upgrade head
cd backend
/tmp/market-speculation-py312/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the Alembic upgrade whenever the schema changes. Backend startup seeds configured markets, tries public data sources, and falls back where needed, but it no longer creates tables implicitly.

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
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/threex
CORS_ORIGINS=["http://localhost:3000"]
API_INTERNAL_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

Useful optional variables:

- `EIA_API_KEY`: enables EIA U.S. grid demand and generation calls.
- `ENTSOE_TOKEN`: enables live ENTSO-E Net Transfer Capacity enrichment of the grid topology. Without it, the canonical seed bundle is used.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`: enables Gemini news-context scoring for the risk engine. Without it, the app uses deterministic heuristic scoring.
- `LLM_SCORER_PROVIDER`: news scorer backend, default `heuristic`. Supported values are `heuristic`, `gemini`, and `domain`.
- `DOMAIN_SCORER_MODEL_DIR`: LoRA adapter directory for `LLM_SCORER_PROVIDER=domain`, default `models/news_scorer_lora`.
- `ACTIVE_FORECASTER`: forecast backend, default `gbr`. Supported values are `gbr`, `chronos`, and `naive_persistence_24h`.
- `CHRONOS_DEVICE_MAP`: Chronos-Bolt inference device, default `cpu`. Use `cuda` on GPU hosts or `mps` on Apple Silicon.
- `CHRONOS_USE_SMALL`: when `true`, uses `amazon/chronos-bolt-small`; otherwise Chronos uses the lighter `amazon/chronos-bolt-tiny`.
- `JWT_SECRET`: HS256 signing secret for API bearer tokens. Change this outside local development.
- `DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD`: seeded analyst account used for local login after migrations.
- `FORECAST_CACHE_TTL_MINUTES`: forecast cache TTL, default `15`.
- `DATA_REFRESH_INTERVAL_MINUTES`: background refresh interval, default `30`.
- `DEMO_MODE`: when `true`, permits computed/synthetic fallback data without marking the market degraded. Defaults to `false`.

For a lightweight local SQLite database, set `DATABASE_URL=sqlite:///./threex.db` and still run `alembic -c alembic.ini upgrade head` before starting the backend.
Except for `/api/health` and `/api/auth/*`, API routes require `Authorization: Bearer <token>` from `POST /api/auth/login`.

## Historical Backfill

A rerunnable historical backfill path keeps the existing hourly timestamp dedupe, so it is safe to run more than once.

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

## Backtesting

The walk-forward backtest scores the active forecaster's MAE / RMSE / directional accuracy / spike F1 against three baselines (persistence, persistence-24h, climatology), produces hour-of-day and regime breakdowns, and computes a PIT calibration histogram.

```bash
cd backend
PYTHONPATH=. python3 scripts/backtest.py --market GB_POWER --lookback-days 365
PYTHONPATH=. python3 scripts/backtest.py --market GB_POWER --compare gbr,chronos
PYTHONPATH=. python3 scripts/render_report.py backend/reports/backtest_GB_POWER_<stamp>.json
```

The checked-in GB_POWER report at `backend/reports/backtest_GB_POWER_20260507_2112.json` covers a 365-day lookback with 49,896 forecasted hourly samples. It shows:

- model RMSE: `21.79` £/MWh,
- persistence-24h RMSE: `33.76` £/MWh,
- climatology RMSE: `48.72` £/MWh,
- 1-hour persistence RMSE: `12.69` £/MWh,
- PIT max deviation from uniform: `0.2881`, so intervals are still too narrow.

The current forecaster beats day-ahead persistence and climatology, but not the simplest 1-hour persistence baseline yet. The PIT result is a known calibration gap; the regime-conditional residual σ work (frontier-B.1) closes part of it on volatile markets.

## LLM Coefficient Ablation

`scripts/risk_ablation.py` re-runs the risk engine on every hour of a market's lookback window twice — once with the LLM coefficients live, once with them forced to neutral — and computes the Kupiec POF test on each. Use it to verify whether the LLM scoring layer actually improves calibration on a given market.

```bash
cd backend
PYTHONPATH=. python3 scripts/risk_ablation.py --market GB_POWER --lookback-days 90
```

Outputs `backend/reports/ablation_<market>_<date>.json`.

## Domain News Scorer Training

The structured news scorer can run as a LoRA fine-tune of `meta-llama/Llama-3.1-8B-Instruct` (or `Qwen2.5-7B-Instruct` when Llama is gated). Runtime dependencies stay lean; training dependencies live in `backend/requirements-train.txt`.

GPU expectation: ~24 GB VRAM.

```bash
cd backend
python -m pip install -r requirements-train.txt
PYTHONPATH=. python3 scripts/build_news_dataset.py --target-rows 5000
PYTHONPATH=. python3 scripts/finetune_news_scorer.py --dry-run
PYTHONPATH=. python3 scripts/finetune_news_scorer.py --model-id meta-llama/Llama-3.1-8B-Instruct
```

The dry run validates prompt formatting and writes `backend/models/news_scorer_lora/training_manifest.json`. A real run writes the LoRA adapter files into the same directory. Set `LLM_SCORER_PROVIDER=domain` at runtime to use them.

## Grid Topology

A canonical 13-bus / 13-line topology covers every priced market. Generate / regenerate the JSON artifact:

```bash
cd backend
PYTHONPATH=. python3 scripts/ingest_grid_topology.py
```

When `ENTSOE_TOKEN` is set, ENTSO-E Net Transfer Capacities are spliced into the European interfaces. Otherwise the seed values are used.

## Docker Compose

```bash
make deploy
```

This starts:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/api`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- OpenTelemetry collector: OTLP gRPC `localhost:4317`, OTLP HTTP `localhost:4318`
- Worker: Redis-backed `arq` process for market refresh, hourly P&L fill, and nightly backtests

The backend container runs Alembic migrations before starting Uvicorn. The worker waits for the backend healthcheck so those migrations are complete before jobs run. The frontend uses `API_INTERNAL_BASE_URL` for server-side container calls and `NEXT_PUBLIC_API_BASE_URL` for browser-side requests, so the browser should call `localhost` while the Next.js server can call the backend container hostname.

## Key API Endpoints

**Markets & data**

- `GET /api/health`
- `GET /api/markets`
- `GET /api/markets/{market_id}`
- `GET /api/markets/{market_id}/prices?limit=720`
- `GET /api/markets/{market_id}/history?from=&to=`
- `GET /api/markets/{market_id}/timeseries?series=demand,wind,solar`
- `GET /api/markets/{market_id}/forecast`
- `GET /api/markets/{market_id}/events`
- `GET /api/markets/{market_id}/news`
- `GET /api/markets/{market_id}/alerts`
- `GET /api/markets/{market_id}/backtest/latest`
- `GET /api/markets/{market_id}/risk-calibration`
- `GET /api/dashboard/{market_code}?history_hours=720`
- `GET /api/events`
- `GET /api/news/sources`
- `POST /api/articles/ingest`
- `POST /api/forecasts/run?market_code=ERCOT_NORTH`
- `POST /api/markets/{market_code}/refresh`

**Risk**

- `POST /api/risk-assessment`
- `POST /api/risk-assessment/solve` — position-sizing solver (caller specifies `max_risk_gbp`, returns the largest matching position)
- `POST /api/risk-assessment/sensitivity` — perturbation table per coefficient
- `POST /api/risk-assessment/paths` — sub-sample of simulated price paths for the path-fan view
- `POST /api/risk-assessment/optimal-hedge` — hedge ratios from the trained deep-hedging policy
- `POST /api/portfolio-risk` — joint MC across positions, returns aggregate + per-position contributions

**Decisions**

- `POST /api/decisions` — log a trade decision (snapshot of the three numbers + thesis text)
- `GET /api/decisions`
- `PATCH /api/decisions/{id}` — close or update
- `DELETE /api/decisions/{id}`

**Grid**

- `GET /api/grid/topology`
- `GET /api/grid/flows`

Example risk request with a cross-zone basis trade:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/risk-assessment \
  -H 'Content-Type: application/json' \
  -d '{
    "market_code": "GB_POWER",
    "position_gbp": 10000,
    "horizon_hours": 24,
    "direction": "long",
    "basis_against_market_code": "EPEX_DE",
    "basis_direction": "long"
  }'
```

## Risk Engine

`POST /api/risk-assessment` converts a market, position size, direction, and horizon into:

- `risk_gbp`: 95 percent empirical CVaR downside estimate,
- `likely_gbp`: expected P&L,
- `upside_gbp`: 95th-percentile upside estimate,
- path-dependent fields such as probability of loss and max drawdown,
- supporting volatility, confidence, regime, catalyst severity, asymmetry, FX, congestion overlay, and rationale fields.

The risk engine uses Monte Carlo simulation, regime-conditional residual volatility, recent events, native market currencies, FX conversion to GBP, the cross-market correlation matrix (for basis trades), the congestion overlay (when the bus's outgoing line is highly utilised), and scored article context. If no LLM API key is configured, it uses a deterministic heuristic scorer.

### Coefficient transparency

Every parameter that flows into the three headline numbers is exposed in the response under `coefficients.items`, grouped into:

- `forecast`: spot, forecast point, model σ, MAE, directional accuracy.
- `realised_vol`: hourly σ, sample size, realised-vs-model blend weight, blended σ at horizon.
- `llm`: tail multiplier, asymmetry, catalyst severity, asymmetry-driven drift, total drift, regime, LLM confidence, CVaR multiplier.
- `fx`: native price currency and the conversion rate to GBP.
- `position`: GBP notional, native notional, hedge ratio, direction sign, horizon, Monte Carlo path count.
- `result`: σ used, expected return, P(loss), edge score, max drawdown, congestion multiplier.

Each item carries a `label`, numeric `value`, `unit`, and one-line `description`. The dashboard renders the block as a Bloomberg-style grouped table, alongside the equation summary that ties them together.

## Data Provenance

Dashboard responses include:

- `key_metrics.data_freshness_minutes`: age of the newest price point in minutes.
- `key_metrics.synthetic_share_24h`: fraction of the last 24 hours using computed or synthetic price sources.
- `key_metrics.backtest_rmse_model`, `backtest_rmse_persistence_24h`, `backtest_calibrated`, `backtest_breach_rate_realized`: latest backtest summary.
- `market.data_status`: `ready` or `degraded`.

The dashboard surfaces these as a data-quality strip and a backtest strip at the top of every market view. When `data_status="degraded"`, the risk panel hides the headline risk numbers and recommends a refresh or backfill rather than presenting synthetic-driven risk as market-grade.

## Event And News Intelligence

The event pipeline stores raw `news_articles`, extracts structured `events` with zone, magnitude_mw, and duration distributions, finds historical analogues, and estimates price impact with explicit uncertainty. Current event types include:

- generator outage,
- transmission outage,
- extreme weather alert,
- renewable forecast revision,
- demand shock,
- regulatory or policy announcement.

RSS ingestion pulls recent articles from public energy sources and avoids duplicate source URLs. Seeded articles provide demo-ready market context even without external feeds.

## Frontend Pages

- `/`: live multi-market ticker, market cards, range-selectable history chart (`1D | 1W | 1M | 1Y | 2Y | Max`), latest forecast, data-quality + backtest strips, and event context.
- `/markets/{marketCode}`: market workbench. Resizable two-row layout. Top row: KLineCharts chart with drawing tools and demand / wind / solar / event overlays, path-fan beneath, and an assessment column with risk panel + risk decomposition table + sensitivity ladder. Bottom row: signals, news, events, calibration badge, position blotter + decision diary.
- `/grid`: DC-OPF topology view with LMP-shaded buses, utilisation-coloured edges, and binding-line highlighting.
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
npx tsc --noEmit
```

## Demo Flow

1. Open `/` and scan the multi-market ticker and market cards.
2. Click into a market (e.g. `GB_POWER`) to open the workbench.
3. Drag the chart range buttons: `1D`, `1W`, `1M`, `1Y`, `2Y`, or `Max`.
4. Adjust position size, horizon, direction in the risk panel — or toggle "Risk-first sizing" and enter a max-risk number instead.
5. Inspect the decomposition table: every coefficient that drove the three numbers, with units and descriptions.
6. Scrub the sensitivity-ladder heatmap to see which inputs matter most.
7. Save a thesis to the decision diary; close it later to compare realized vs predicted P&L.
8. Open `/grid` to inspect inter-zone flows, LMPs, and binding lines.
9. Visit `/events` and `/developer` for event feed and endpoint reference.

## Notes And Caveats

- This is a decision-support tool, not financial advice.
- Some market data is computed or synthetic when public APIs are unavailable or unauthenticated. The UI labels this explicitly.
- U.S. real historical data requires `EIA_API_KEY`; otherwise U.S. markets are marked degraded outside demo mode.
- European spot prices have no free hourly feed currently wired; prices fall back to the merit-order model using real weather inputs.
- Local SQLite databases such as `backend/threex.db` are ignored by git; production-style runs should use Postgres via `DATABASE_URL`.
- The frontend has both server-side and browser-side API calls, so keep `API_INTERNAL_BASE_URL` and `NEXT_PUBLIC_API_BASE_URL` distinct when running in containers.
- Backend logs are emitted as JSON via structlog. OpenTelemetry traces use the console exporter by default; set `OTEL_EXPORTER_OTLP_ENDPOINT` to send spans to an OTLP collector.
- SlowAPI rate limiting is enabled by default: authenticated data endpoints use a 60 req/min per-user default, `/risk-assessment` uses 10 req/min, and `/risk-assessment/sensitivity` uses 5 req/min.

## Roadmap

The live roadmap lives in `FRONTIER.md`. Phases A–E are complete; Phase F (enterprise hardening) is underway:

- Postgres + Alembic migrations in place of `Base.metadata.create_all`.
- JWT auth (per-user decisions and positions) and rate limiting.
- Append-only signed audit log for compliance export.
- PDF + Excel exports of the full risk-assessment pack (coefficients, path fan, calibration record, FX provenance, scenarios).
- OpenTelemetry instrumentation + structured logging.
- Redis-backed background workers (`arq`) for refresh, backtest, and P&L-fill jobs.
- WebSocket push (`/ws/markets/{code}`) for price ticks, forecast revisions, new events, alerts, and recomputed risk.
- SOC2 prep documentation.

One blocker remains in `FRONTIER.md`: `frontier-D.6` (golden-set validation of the domain LoRA scorer) needs a GPU host to run the real LoRA fine-tune.
