# Frontier roadmap — 6 phases

Six phases of work taking the platform from "MVP with the math correct" to "decision-grade analytics, enterprise-ready." Phases are ordered to ship the user-visible coefficient-transparency story first, then back-fill the deeper technical work that makes it credible. Execute strictly top-to-bottom: A → B → C → D → E → F. Each phase ends with an acceptance gate.

The original `PLAN.md` Phases 1–4 are complete. Phases 5–10 from PLAN are absorbed into this file at the positions noted below.

Convention: every sub-step is one commit titled `frontier-X.N: short description`. Tests must be green before advancing.

---

## Phase A — Glass-box UX (the three numbers become the product)

Make `risk_gbp / likely_gbp / upside_gbp` the gravitational centre of every interaction. Position-sizing solver, sensitivity ladder, calibration badge, decision diary, path-fan, KLineCharts migration with overlays, resizable multi-panel layout. Absorbs PLAN Phase 6 and the unfinished pieces of PLAN Phase 8.

### A.1 Position-sizing solver
- `POST /api/risk-assessment/solve` accepting `{market_code, max_risk_gbp, horizon_hours, direction, position_unit}`. Server runs binary search (≤12 iterations, 5,000 paths each) on `position_gbp` until `risk_gbp` is within ±2% of `max_risk_gbp`. Returns the resolved request body and the full assessment.
- Frontend: "Risk-first sizing" toggle in `RiskPanel` swapping the position-size input for a max-risk input.

### A.2 Sensitivity ladder
- `POST /api/risk-assessment/sensitivity` accepts the standard request body plus `coefficients_to_perturb`. For each named coefficient, re-run the assessment at −50%, −25%, 0%, +25%, +50% (others held constant). Returns a 2-D table `coefficient × perturbation → {risk_gbp, likely_gbp, upside_gbp}`.
- Frontend: `risk-sensitivity-ladder.tsx` rendering the table as a heatmap.

### A.3 Calibration badge
- New table `risk_assessment_log(timestamp, market_id, position_gbp, direction, horizon_hours, risk_gbp, likely_gbp, upside_gbp, realized_pnl_gbp NULLABLE)`. Hourly filler updates matured rows.
- `GET /api/markets/{id}/risk-calibration` returns rolling-30-day actual breach rate vs claimed (5%), Kupiec POF p-value, sample count, `calibration_status: "honest" | "understating" | "overstating"`.
- Frontend badge under the three numbers.

### A.4 Decision diary
- Reuse `risk_assessment_log` with `kind: "diary" | "auto"` and a `thesis_text` column.
- `POST /api/decisions` and `GET /api/decisions`.
- `decision-diary.tsx` panel showing past decisions with realized vs predicted percentile when matured.

### A.5 Path-fan visualization
- `POST /api/risk-assessment/paths` returning a sub-sample of 200 simulated price paths.
- `risk-path-fan.tsx` renders the fan as overlaid polylines plus three horizontal P&L lines.

### A.6 KLineCharts migration + overlays (absorbs PLAN Phase 6)
- `klinecharts@9` installed. New `kline-price-chart.tsx` wraps the imperative API behind a React component with built-in drawing tools (trendline, level, range box).
- Custom indicators: `wind_share`, `solar_share`, `event_markers`.
- `GET /api/markets/{id}/timeseries?series=demand,wind,solar` returns aligned hourly series.

### A.7 Resizable multi-panel layout (absorbs PLAN Phase 8 layout work)
- `react-resizable-panels` installed. Workbench split into a vertical PanelGroup of two horizontal rows; sizes persisted to `localStorage`.

### Phase A acceptance
- Risk panel defaults to risk-first input mode.
- Sensitivity ladder, calibration badge, decision diary, path fan, KLineCharts chart with overlays, and resizable multi-panel layout all live on the workbench.

## Phase B — Foundation-model forecast + calibration (absorbs PLAN Phase 5)

Replace gradient boosting with a foundation-model forecaster (Chronos-Bolt). Make residual σ regime-aware. Prove via backtest ablation that LLM coefficients in the risk engine improve calibration.

### B.1 Regime-conditional residual σ (PLAN Phase 5)
- New `app/forecasting/regime.py` exposing `classify_regime(row) -> "calm"|"trending"|"stressed"`.
- Train per-regime residual std in `GradientBoostingForecastModel.train()`; store `self.residual_std_by_regime`. At forecast time, classify the input row and pick σ by regime.
- Persist `regime` and chosen σ into `feature_snapshot_json["sigma_price"]`.

### B.2 Pluggable forecaster registry
- `forecaster_registry: dict[str, Callable[[], ForecastModel]]` keyed by `"gbr"`, `"chronos"`, `"naive_persistence_24h"`.
- `forecast_service.py` reads the active forecaster name from `settings.active_forecaster` (default `"gbr"`).

### B.3 Chronos-Bolt forecaster
- `chronos-forecasting` added to deps.
- `chronos_model.py` implementing the `ForecastModel` Protocol using `amazon/chronos-bolt-tiny` by default; `amazon/chronos-bolt-small` behind a flag.
- `predict_distribution` samples 100 paths and computes empirical quantiles for `lower_bound`, `upper_bound`, `sigma_price`.

### B.4 Multi-forecaster backtest
- `walk_forward_backtest` takes `forecaster_names: list[str]` and runs each in one pass. Output adds `vs_forecasters` shaped like `vs_baselines`.
- `scripts/backtest.py` accepts `--compare gbr,chronos`.

### B.5 LLM-coefficient ablation harness
- `app/services/risk_ablation.py` re-runs the risk engine on every hour of the lookback window twice: with LLM coefficients live, and with `tail_multiplier=1.0, asymmetry=0.0, catalyst_severity=0.0` forced. Returns `breach_rate_with_llm`, `breach_rate_without_llm`, Kupiec POF p-values, sample count, per-regime breakdown.
- `scripts/risk_ablation.py` writes `backend/reports/ablation_<market>_<date>.json`.

### B.6 Backtest report HTML
- `scripts/render_report.py` turns a JSON report into a single-file HTML via Jinja2. Sections: headline metrics, vs baselines, vs forecasters, hour-of-day breakdown, regime breakdown, PIT histogram (inline SVG), LLM ablation.

### B.7 Surface latest backtest in API + dashboard
- `GET /api/markets/{id}/backtest/latest` returns the most recent JSON report (or null).
- Dashboard `key_metrics` extended with `backtest_rmse_model`, `backtest_rmse_persistence_24h`, `backtest_calibrated`, `backtest_breach_rate_realized`. Frontend renders a strip near the data-quality strip.

### Phase B acceptance
- Real backtest run for GB_POWER comparing `gbr` vs `chronos` lives in `backend/reports/`.
- Ablation report for GB_POWER exists.
- Calibration badge flips to green for at least one market.

## Phase C — Deep hedging + portfolio risk

Replace the manual `hedge_ratio` slider with an optimal hedge ratio learned by a small neural net trained against the simulator. Aggregate risk across multiple positions with proper correlation. Add the position blotter (PLAN Phase 8 finish).

### C.1 Cross-market correlation matrix
- `app/services/correlation.py` computes the pairwise hourly-return correlation matrix across all markets, cached for 6 hours.

### C.2 Portfolio risk endpoint
- `POST /api/portfolio-risk` accepting a list of positions. Server runs a joint Monte Carlo: shocks drawn from a multivariate distribution with the correlation matrix, then applied per-market. Aggregates pnl across positions, returns portfolio-level three numbers plus per-position contributions.

### C.3 Deep hedging policy
- `app/services/deep_hedger.py`. Policy is a 3-layer MLP taking `[spot, sigma_hourly, drift_hourly, tail_multiplier, asymmetry, catalyst_severity, horizon_hours]` and outputting a `hedge_ratio` in `[0, 1]` per market. Trained against the simulator: minimise CVaR_95 of resulting portfolio pnl over 50,000 sampled scenarios.
- `scripts/train_deep_hedger.py` saves `backend/models/deep_hedger.pt`.
- `POST /api/risk-assessment/optimal-hedge` uses the trained policy.

### C.4 Hedge suggestion in UI
- When `risk_gbp > threshold`, surface "Suggested hedge: …" with the resulting risk drop and expected likely_gbp cost.

### C.5 Multi-position blotter (PLAN Phase 8 finish)
- `position-blotter.tsx` panel: open positions, individual three numbers, portfolio aggregate at the bottom. CRUD via `/api/decisions` (extended with `is_open: bool` and `closed_at`).

### Phase C acceptance
- Portfolio risk endpoint live.
- Deep hedger trained and beating random on held-out test.

## Phase D — Domain LLM fine-tune + structured event schema (absorbs PLAN Phase 7)

Replace heuristic + Gemini news scorer with a domain-fine-tuned model. Structured event schema with zone / magnitude / duration distributions. Historical analogue matching.

### D.1 Curated training set
- `scripts/build_news_dataset.py` scrapes FERC eLibrary daily filings, ENTSO-E transparency unavailability messages, ELEXON BOA dataset comments, and the RSS feeds in `news_rss.py`. Falls back to deterministic source-family templates when sources are unavailable.
- Output: `backend/data/news_train.jsonl` (≥ 5,000 rows). Silver labels bootstrapped via the current Gemini scorer.

### D.2 LoRA fine-tune
- `scripts/finetune_news_scorer.py` LoRA-tunes `meta-llama/Llama-3.1-8B-Instruct` (or `Qwen2.5-7B-Instruct` if Llama is gated). Training deps in `backend/requirements-train.txt`. GPU expectation: ≥ 24 GB VRAM.
- Output: `backend/models/news_scorer_lora/`. Dry-run path writes a manifest without weights.

### D.3 Domain LLM provider
- `app/services/llm_scorer.py` gains a `"domain"` provider that lazy-loads the LoRA adapter. Selection via `settings.llm_scorer_provider = "domain" | "gemini" | "heuristic"`.

### D.4 Structured event schema
- Migration adds `zone`, `node`, `magnitude_mw`, `duration_hours_estimate`, `duration_hours_p10`, `duration_hours_p90`, `analogue_event_ids`, `classifier_version` to `events`. `capacity_impact_mw` retained for backward compat.
- `extract_primary_event` populates the new fields when the classifier returns them.

### D.5 Historical analogue matching
- `app/services/event_analogues.py` with `find_analogues(event, db, k=5)` returning the 5 past events with highest cosine similarity on `[event_type_one_hot, magnitude_mw, hour_of_day, day_of_week, regime_one_hot]`.

### D.6 Validation on golden set
- Hand-curated 50-article golden set in `backend/tests/data/news_golden.jsonl`. Test asserts the fine-tuned scorer beats heuristic by ≥ 15 percentage points.

### Phase D acceptance
- Domain LLM scorer is the default in `.env.example`.
- Structured event schema in place; analogues visible in UI.
- Fine-tuned scorer beats heuristic on golden set.

## Phase E — Real grid topology + DC-OPF for cross-zone trades

Model congestion between zones so the simulator prices basis trades correctly.

### E.1 Topology ingest
- `scripts/ingest_grid_topology.py` pulls PJM Data Miner topology, ERCOT MIS topology, NYISO open-access tariff data, and ENTSO-E cross-border capacities. Falls back to a canonical 13-bus / 13-line seed bundle when sources are unavailable.
- Output: `backend/data/grid_topology.json` + `grid_node`, `grid_edge` tables.

### E.2 DC-OPF solver
- `app/grid/dc_opf.py` implements vanilla DC OPF as a linear program using `scipy.optimize.linprog` (HiGHS). Inputs: node loads, generation capacity, edge thermal limits. Outputs: line flows, LMPs (from constraint duals), binding-line set.

### E.3 Cross-zone basis trade type
- `RiskAssessmentRequest` accepts optional `basis_against_market_code` and `basis_direction`. When set, the simulator runs paired paths for both markets using the C.1 correlation matrix and reports spread P&L.

### E.4 Congestion-aware risk
- DC-OPF runs across a coarse load-multiplier grid per market and produces a per-market σ-multiplier curve. The risk engine multiplies `sigma_hourly` by the lookup at the current tightness ratio.

### E.5 Topology UI
- `/grid` Next.js route renders the topology graph with bus colour shaded by LMP, line colour and stroke by utilisation, bold red for binding lines.
- Backend: `GET /api/grid/topology` (seed bundle verbatim) and `GET /api/grid/flows` (DC-OPF result with flows, LMPs, binding-line flags).

### Phase E acceptance
- Basis trades quotable end-to-end.
- DC-OPF runs in < 50 ms for a 50-node sub-network.

## Phase F — Enterprise hardening (absorbs PLAN Phase 9 + 10)

Auth, audit log, Postgres + Alembic, observability, exports, deployment-ready, SOC2 prep.

### F.1 Postgres + Alembic
- Read `DATABASE_URL`. `alembic init backend/alembic`. Generate baseline migration from current models; convert prior partial migrations into proper Alembic revisions.
- Stop calling `Base.metadata.create_all` in `main.py`.

### F.2 JWT auth
- `fastapi-users` JWT backend wired to the existing `User` model. Endpoints behind `Depends(current_user)`. Per-user `Decision` / `Position` rows.

### F.3 Audit log
- All API mutations write to `audit_log(actor, action, target, before, after, signed_hash)` with hash chaining for tamper-evidence.
- `GET /api/audit?from=&to=` for compliance export.

### F.4 PDF + Excel export
- `POST /api/risk-assessment/export?format=pdf|xlsx` returns a downloadable file: timestamp, full coefficients, path-fan SVG, calibration record, FX provenance, scenarios.

### F.5 OpenTelemetry observability
- OTel instrumentation on FastAPI + SQLAlchemy + httpx. Console exporter by default; OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- Structured JSON logs via `structlog`.

### F.5.1 Rate limiting (PLAN Phase 10 finish)
- `slowapi` middleware. 60 req/min per user on data endpoints; 10 req/min on `/risk-assessment`; 5 req/min on `/risk-assessment/sensitivity`.

### F.6 Docker Compose deployment
- `infrastructure/docker-compose.yml` includes Postgres + Redis + backend + frontend + OTel collector. `make deploy` brings the stack up on a fresh Linux box.

### F.6.1 Background workers (PLAN Phase 9 finish)
- Move `_refresh_all_markets`, the nightly backtest job, and the hourly P&L-fill job to `arq` (Redis-backed). Workers run as a separate process in Compose. Retries with exponential backoff.

### F.7 WebSocket push (PLAN Phase 8 finish)
- `app/api/ws.py` exposing `/ws/markets/{code}` pushing `price_tick`, `forecast_revision`, `new_event`, `alert`, `risk_recomputed` JSON messages from a Redis pub/sub populated by the workers above.
- Frontend `lib/use-market-stream.ts` hook applies ticks to KLineCharts via `updateData`.

### F.8 SOC2 prep documentation
- `docs/SOC2.md` covers audit log, encryption at rest + transit, secret management, access control, change management, incident response stub, vendor list.

### Phase F acceptance
- App runs in Docker Compose with Postgres + Redis + OTel.
- All requests authenticated; mutations audit-logged.
- Export pack works end-to-end.
- WebSocket push delivers ticks to a connected browser.

---

## Out of scope

- Mobile UI.
- Trade-execution / OMS layer (booking actual trades into a broker).
- Richer alerts UX beyond what `frontend/components/alerts-panel.tsx` already does.

## Progress log

Format: `frontier-X.N (sha) — one-line result.`

- frontier-A.1 (d00d8fc) — Position-sizing solver endpoint and risk-first panel mode.
- frontier-A.2 (6409051) — Sensitivity endpoint and workbench heatmap.
- frontier-A.3 (2360e00) — Calibration logging, P&L fill, badge payload, workbench badge.
- frontier-A.4 (689db77) — Decision-diary endpoints, save modal, maturity update, workbench panel.
- frontier-A.5 (b303ba7) — Path-fan endpoint and SVG workbench visualization.
- frontier-A.6 (a51119f) — KLineCharts workbench wrapper, fundamentals timeseries API, wind/solar/event overlays.
- frontier-A.7 (ce5d208) — Persisted resizable workbench layout, chart/risk top row, supporting bottom row.
- frontier-B.1 (37c914d) — Regime classifier extracted; per-regime residual σ trained and persisted into forecast snapshots.
- frontier-B.2 (c7959e7) — Forecaster registry, active-forecaster setting, naive 24h persistence forecaster.
- frontier-B.3 (60d362e) — Chronos-Bolt forecaster adapter, dependency/config docs.
- frontier-B.4 (30aeca4) — Multi-forecaster walk-forward backtest, `--compare` CLI flag.
- frontier-B.5 (08d3d7e) — LLM coefficient ablation service, Kupiec POF, CLI report writer.
- frontier-B.6 (53fdedb) — Jinja2 single-file report renderer, inline PIT SVG, GB_POWER HTML artifact.
- frontier-B.7 (5f32632) — Latest-backtest API endpoint, dashboard backtest metrics + strip.
- frontier-B.acceptance (39ff6a3) — GB_POWER gbr-vs-chronos backtest + ablation reports; calibration honest on EPEX_DE; SQLite risk-log compatibility bridge.
- frontier-C.1 (0fe34be) — 6-hour-cached cross-market hourly-return correlation matrix.
- frontier-C.2 (f27da61) — Portfolio-risk endpoint with correlated Monte Carlo aggregation and per-position contributions.
- frontier-C.3 (1bed5f0) — Deep-hedging MLP, training script, policy artifact, optimal-hedge endpoint.
- frontier-C.4 (a1ddac0) — Risk-panel hedge suggestion UI wired to optimal-hedge.
- frontier-C.5 (8ea9588) — Open-position blotter backed by decision CRUD and portfolio aggregate.
- frontier-C.acceptance (9e25e9b) — Portfolio-risk endpoint live; workbench shows aggregate / per-position blotter; deep hedger beats random on held-out scenarios.
- frontier-D.1 (689e088) — News corpus builder; 5,000-row silver-labelled training JSONL.
- frontier-D.2 (ae9d544) — LoRA fine-tune harness, training deps, GPU docs, dry-run manifest.
- frontier-D.3 (b224add) — Configurable domain / gemini / heuristic scorer provider with lazy LoRA loading.
- frontier-D.4 (1b2e678) — Structured event schema fields; extractor population; SQLite compatibility migration.
- frontier-D.5 (a6b0cbf) — Historical analogue matcher, analogue API endpoint, ingest/read population, event-feed surfacing.
- frontier-D.6-wip (pending) — 50-row golden set, validation harness, and CLI are in place; real adapter comparison skips until LoRA weights exist.
- frontier-E.2 (3523d41) — DC-OPF solver (scipy HiGHS LP, nodal-susceptance B_bus formulation, dual-based LMPs, binding-line detection).
- frontier-E.1 (f9a703d) — Topology loader + canonical 13-bus / 13-line seed bundle covering all 9 priced markets; `ingest_grid_topology.py` runner; ENTSO-E NTC enrichment stubbed behind `ENTSOE_TOKEN`.
- frontier-E.3 (4f2705a) — Cross-zone basis trade type; engine runs paired correlated MC; spread P&L on combined position.
- frontier-E.4 (68f9b47) — Congestion-aware σ overlay; per-market DC-OPF over 9 load multipliers; `congestion_multiplier` coefficient surfaced.
- frontier-E.5 (87a725e) — Grid topology UI at `/grid`; `/api/grid/topology` + `/api/grid/flows` endpoints.
- frontier-F.1 (pending) — Postgres `DATABASE_URL` path, Alembic baseline migration, and startup/scripts moved off `Base.metadata.create_all`; backend pytest 104 passed, 1 skipped.
- frontier-F.2 (pending) — JWT auth endpoints, protected API routes, seeded demo user, and per-user decision ownership; backend pytest 108 passed, 1 skipped.
- frontier-F.3 (pending) — Hash-chained audit log table, mutation audit writes, and `/api/audit` export; focused backend pytest 19 passed.
- frontier-F.4 (pending) — Risk export endpoint returns audited PDF/XLSX packs; risk panel exposes export buttons. Tests: export + audit focused pass; tsc pass.
- frontier-F.5 (pending) — OpenTelemetry tracing for FastAPI/SQLAlchemy/httpx with console-or-OTLP export; structlog JSON logging. Tests: observability focused pass.
- frontier-F.5.1 (pending) — SlowAPI per-user data limits plus stricter risk-assessment and sensitivity throttles. Tests: rate-limit focused pass.
- frontier-F.6 (pending) — Deployment Compose stack for Postgres, Redis, backend, frontend, and OTel collector; `make deploy` target. Tests: YAML structure pass; Docker unavailable locally.
- frontier-F.6.1 (pending) — BackgroundScheduler removed; arq worker owns market refresh, hourly P&L fill, and nightly backtests with retry backoff. Tests: worker focused pass.

## Blockers

Format: `frontier-X.N — short description. To unblock: …`

- frontier-D.6 — Golden-set validation harness now exists, but the required real domain LoRA adapter weights are still missing; current D.2 output is a dry-run manifest because the local environment lacks a 24 GB-class GPU and authenticated gated-model access. **To unblock:** run `PYTHONPATH=. python3 scripts/finetune_news_scorer.py --model-id meta-llama/Llama-3.1-8B-Instruct` on a suitable GPU host (or `--model-id Qwen/Qwen2.5-7B-Instruct` if Llama access is gated), commit `adapter_config.json`, `adapter_model.safetensors`, and tokenizer files under `backend/models/news_scorer_lora/`, then run `PYTHONPATH=. python3 scripts/validate_news_scorer.py`.
