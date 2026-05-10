Frontier roadmap — 6 phases, ~6 months
The phases are ordered to ship the user-visible "coefficient transparency" pitch first, then back-fill the deep technical work that makes it credible. Execute strictly top-to-bottom: A → B → C → D → E → F. Each phase ends with an acceptance gate; do not advance until it passes.

The original PLAN.md Phases 1–4 are complete and committed. Phases 5–10 from PLAN are absorbed into this file at the positions noted; do not also work from PLAN.

Phase A — Glass-box UX (the three numbers become the product)
Goal. Make risk_gbp / likely_gbp / upside_gbp the gravitational centre of every interaction. Position-sizing solver, sensitivity ladder, calibration badge, decision diary, path-fan, KLineCharts migration with overlays, and a resizable multi-panel layout. Absorbs PLAN Phase 6 and the unfinished pieces of PLAN Phase 8.

A.1 Position-sizing solver
New endpoint POST /api/risk-assessment/solve accepting {market_code, max_risk_gbp, horizon_hours, direction, position_unit}.
Server runs a binary search (max 12 iterations, 5,000 paths each) on position_gbp until risk_gbp is within ±2% of max_risk_gbp. Returns the resolved request body and the full assessment.
Tests: assert solver converges within tolerance for a known σ; assert monotonicity (larger max_risk_gbp → larger resolved position).
Frontend: "Risk-first sizing" toggle in RiskPanel swapping the position-size input for a max-risk input; on change, calls the new endpoint and hydrates the panel with the solver result.
Commit: frontier-A.1: position-sizing solver.
A.2 Sensitivity ladder
New endpoint POST /api/risk-assessment/sensitivity accepting the standard request body plus a coefficients_to_perturb list. For each named coefficient (tail_multiplier, asymmetry, catalyst_severity, sigma_hourly, drift_hourly, fx_to_gbp, hedge_ratio), re-run the assessment with that coefficient perturbed at −50%, −25%, 0%, +25%, +50% (others held constant). Returns a 2-D table coefficient × perturbation → {risk_gbp, likely_gbp, upside_gbp}.
Tests: assert monotonic relationships where they exist (more tail_multiplier → more risk_gbp).
Frontend: new component risk-sensitivity-ladder.tsx rendering the table as a heatmap (red = risk grows, green = risk shrinks) with raw values as cell labels. Slot below RiskDecompositionPanel.
Commit: frontier-A.2: sensitivity ladder.
A.3 Calibration badge
New table risk_assessment_log(timestamp, market_id, position_gbp, direction, horizon_hours, risk_gbp, likely_gbp, upside_gbp, realized_pnl_gbp NULLABLE) populated whenever /risk-assessment is hit.
Background filler hourly fills realized_pnl_gbp for matured rows.
New endpoint GET /api/markets/{id}/risk-calibration returning rolling-30-day actual breach rate vs claimed (5%), Kupiec POF p-value, sample count, calibration_status: "honest" | "understating" | "overstating".
Frontend: badge under the three numbers showing Calibration: ✓ honest (4.7% breach vs 5.0% target, 312 reads) or ✗ understating risk (8.3% vs 5.0%).
Tests: synthetic 1,000 logged reads with known breach rate; assert badge text matches.
Commit: frontier-A.3: calibration badge.
A.4 Decision diary
Reuse risk_assessment_log with a kind: "diary" | "auto" discriminator and a thesis_text column.
New endpoints POST /api/decisions and GET /api/decisions.
Frontend decision-diary.tsx panel showing past decisions with realized vs predicted percentile when matured. "Save decision" button on RiskPanel opens a modal for thesis text.
Tests: end-to-end create + list + matured update.
Commit: frontier-A.4: decision diary.
A.5 Path-fan visualization
New endpoint POST /api/risk-assessment/paths returning a sub-sample of 200 simulated price paths (cap response payload).
Frontend risk-path-fan.tsx renders the fan as overlaid polylines with low opacity; three horizontal P&L lines for the three numbers; tooltip showing percentile at the cursor.
Slot above RiskDecompositionPanel.
Commit: frontier-A.5: path-fan visualization.
A.6 KLineCharts migration + overlays (absorbs PLAN Phase 6)
npm i klinecharts@9 in frontend/.
New frontend/components/kline-price-chart.tsx wrapping the imperative KLineCharts API behind a React component with built-in drawing tools (trendline, level, range box).
Custom indicators for wind_share, solar_share, event_markers (triangles by severity, click → tooltip with event details).
New endpoint GET /api/markets/{id}/timeseries?series=demand,wind,solar returning aligned hourly series.
Replace price-forecast-chart.tsx usages on the workbench with KlinePriceChart.
Commit: frontier-A.6: KLineCharts migration + overlays.
A.7 Resizable multi-panel layout (absorbs PLAN Phase 8 layout work)
npm i react-resizable-panels.
Convert workbench to a resizable grid: chart (60%) | risk + decomposition + scenarios (40%) on top row; news | events | calibration | decision diary on bottom row.
Persist user sizes to localStorage.
Commit: frontier-A.7: multi-panel layout.
Phase A acceptance
Risk panel defaults to risk-first input mode.
Sensitivity ladder, calibration badge, decision diary, path fan, KLineCharts chart with overlays, and resizable multi-panel layout all live on the workbench.
All tests green; tsc clean.
FRONTIER.md Progress log updated.
Phase B — Foundation-model forecast + calibration (absorbs PLAN Phase 5)
Goal. Replace gradient boosting with a foundation-model forecaster (Chronos-Bolt). Make residual σ regime-aware. Prove with a backtest ablation that the LLM coefficients in the risk engine actually improve calibration. Phase A ships the calibration badge as a honest indicator; Phase B is what eventually turns it green.

B.1 Regime-conditional residual σ (was PLAN Phase 5)
Lift _classify_regime out of backend/app/forecasting/backtest.py into backend/app/forecasting/regime.py as classify_regime(row: pd.Series) -> "calm"|"trending"|"stressed". Single source of truth.
Train per-regime residual std in GradientBoostingForecastModel.train(); store self.residual_std_by_regime: dict[str, float]. Default fallback to global if any regime has < 24 samples in train.
At forecast time: classify the input row, pick σ by regime. Persist regime and chosen σ into feature_snapshot_json["sigma_price"] so risk_engine.py reads them unchanged.
Tests: same input → same regime; per-regime σ varies; PIT histogram on synthetic regime-switching data is closer to uniform than with a global σ.
Commit: frontier-B.1: regime-conditional residual σ.
B.2 Pluggable forecaster registry
Refactor backend/app/forecasting/ so models implement the existing ForecastModel Protocol at forecasting/base.py.
Add forecaster_registry: dict[str, Callable[[], ForecastModel]] keyed by "gbr", "chronos", "naive_persistence_24h".
forecast_service.py reads the active forecaster name from settings.active_forecaster (default "gbr").
Tests: registry returns a fresh instance per call; switching env produces a different model_version.
Commit: frontier-B.2: pluggable forecaster registry.
B.3 Chronos-Bolt forecaster
Add chronos-forecasting to requirements.txt. Document GPU optionality.
New module backend/app/forecasting/chronos_model.py implementing ChronosForecastModel against the Protocol. Use chronos.ChronosBoltPipeline.from_pretrained("amazon/chronos-bolt-tiny"); defer chronos-bolt-small behind a flag.
Implement predict_distribution by sampling 100 paths from Chronos and computing empirical quantiles for lower_bound, upper_bound, sigma_price.
Wire into the registry under "chronos".
Tests: forecast on the synthetic frame from tests/test_forecast_distribution.py; assert non-zero σ; assert shape (horizon × 4 columns).
Commit: frontier-B.3: chronos-bolt forecaster.
B.4 Multi-forecaster backtest
Extend walk_forward_backtest to take forecaster_names: list[str] and run each in one pass. Output adds vs_forecasters: dict[str, dict[str, float]] shaped like vs_baselines.
Update backend/scripts/backtest.py to accept --compare gbr,chronos and emit the comparison block.
Tests: assert both gbr and chronos results appear in the report.
Commit: frontier-B.4: multi-forecaster backtest.
B.5 LLM-coefficient ablation harness
New module backend/app/services/risk_ablation.py. Public run_risk_ablation(market_code, lookback_days, position_gbp). Re-runs the risk engine on every hour of the lookback window twice: (a) with LLM coefficients live, (b) with tail_multiplier=1.0, asymmetry=0.0, catalyst_severity=0.0 forced. Compute realized P&L from the next-hour move, bin into "would have breached risk_gbp". Returns breach_rate_with_llm, breach_rate_without_llm, kupiec_p_value_with_llm, kupiec_p_value_without_llm, sample count, per-regime breakdown.
Implement Kupiec POF test (LR_uc statistic) — closed form, ~10 lines numpy.
New CLI backend/scripts/risk_ablation.py writing backend/reports/ablation_<market>_<date>.json.
Tests: synthetic data where LLM coefficients are deliberately mis-specified — assert breach rate without LLM is closer to 5%.
Commit: frontier-B.5: LLM coefficient ablation harness.
B.6 Backtest report HTML
backend/scripts/render_report.py that turns one of the JSON reports under backend/reports/ into a single-file HTML using vanilla Jinja2 (add jinja2 to deps explicitly). Sections: headline metrics, vs baselines, vs forecasters, hour-of-day breakdown, regime breakdown, PIT histogram (inline SVG, no chart lib), LLM ablation block.
Output to backend/reports/<json-stem>.html.
Tests: render on a sample; assert HTML contains the expected section headers.
Commit: frontier-B.6: backtest report HTML.
B.7 Surface latest backtest in API + dashboard
GET /api/markets/{id}/backtest/latest returning the most recent JSON report (or null) for that market.
Dashboard key_metrics extended with backtest_rmse_model, backtest_rmse_persistence_24h, backtest_calibrated, backtest_breach_rate_realized. Frontend strip near the existing data-quality strip.
Tests: endpoint returns 200 with a seeded report fixture; tsc clean.
Commit: frontier-B.7: surface backtest in dashboard.
Phase B acceptance
Real backtest run for GB_POWER comparing gbr vs chronos exists in backend/reports/.
Ablation report for GB_POWER exists.
Calibration badge from Phase A flips to green for at least one market.
Tests green.
Phase C — Deep hedging + portfolio risk
Goal. Replace the manual hedge_ratio slider with an optimal hedge ratio learned by a small neural net trained against the simulator. Aggregate risk across multiple positions with proper correlation. Adds the position blotter (PLAN Phase 8 finish).

C.1 Cross-market correlation matrix
New backend/app/services/correlation.py computing the pairwise hourly-return correlation matrix across all markets, cached in-process (Redis-ready) with a 6-hour TTL.
Tests: GB_POWER vs ERCOT_NORTH should have a finite, non-degenerate correlation given the backfilled data.
Commit: frontier-C.1: cross-market correlation.
C.2 Portfolio risk endpoint
POST /api/portfolio-risk accepting a list of positions. Server runs a joint Monte Carlo: shocks drawn from a multivariate normal (or t) with the correlation matrix, then applied per-market. Aggregate pnl across positions, returns portfolio-level three numbers plus per-position contribution breakdown.
Tests: two anti-correlated positions reduce portfolio risk vs sum of individual risks.
Commit: frontier-C.2: portfolio risk endpoint.
C.3 Deep hedging policy
backend/app/services/deep_hedger.py. Policy is a 3-layer MLP (torch — add to deps) taking [spot, sigma_hourly, drift_hourly, tail_multiplier, asymmetry, catalyst_severity, horizon_hours] and outputting a hedge_ratio in [0, 1] for each market. Trained against the simulator: minimize CVaR_95 of resulting portfolio pnl over 50,000 sampled scenarios.
Training script backend/scripts/train_deep_hedger.py (≤ 30 min on CPU for the small net), saves backend/models/deep_hedger.pt.
New POST /api/risk-assessment/optimal-hedge using the trained policy.
Tests: trained policy beats random hedge_ratio on a held-out scenario set.
Commit: frontier-C.3: deep hedging policy.
C.4 Hedge suggestion in UI
When risk_gbp > threshold, show "Suggested hedge: short 60% notional in PJM_WESTERN_HUB → risk drops from £580 to £190, costs £30 in expected likely_gbp." Driven by optimal-hedge.
Commit: frontier-C.4: hedge suggestion UI.
C.5 Multi-position blotter (PLAN Phase 8 finish)
position-blotter.tsx panel: open positions, individual three numbers, portfolio aggregate at the bottom. CRUD via the existing /api/decisions (extend with is_open: bool and closed_at).
Commit: frontier-C.5: position blotter.
Phase C acceptance
Portfolio risk endpoint live; UI shows aggregate + per-position breakdown.
Deep hedger trained and beating random on held-out test.
Phase D — Domain LLM fine-tune + structured event schema (absorbs PLAN Phase 7)
Goal. Replace heuristic + Gemini news scorer with a domain-fine-tuned model. Structured event schema with zone/magnitude/duration distributions. Historical analogue matching.

D.1 Curated training set
backend/scripts/build_news_dataset.py scraping FERC eLibrary daily filings, ENTSO-E transparency unavailability messages, ELEXON BOA dataset comments, Reuters/Argus public RSS headlines from news_rss.py.
Output: backend/data/news_train.jsonl with {text, label_dict}. Aim for ≥ 5,000 labelled rows. Bootstrap labels by running the current Gemini scorer over the corpus and keeping high-confidence outputs as silver labels.
Commit: frontier-D.1: news training corpus builder.
D.2 LoRA fine-tune
backend/scripts/finetune_news_scorer.py LoRA-tuning meta-llama/Llama-3.1-8B-Instruct (or Qwen2.5-7B-Instruct if Llama gated) on the corpus. Use peft + transformers + trl (separate requirements-train.txt because of CUDA pull). Document GPU expectation (24GB recommended) in README.md.
Output: backend/models/news_scorer_lora/.
Commit: frontier-D.2: news scorer LoRA fine-tune.
D.3 Domain LLM provider
Extend backend/app/services/llm_scorer.py with provider "domain" that loads the LoRA adapter at startup. Selection via settings.llm_scorer_provider = "domain" | "gemini" | "heuristic".
Tests: round-trip an inference; assert valid score schema.
Commit: frontier-D.3: domain LLM provider.
D.4 Structured event schema
Migration: add columns to events — zone, node, magnitude_mw, duration_hours_estimate, duration_hours_p10, duration_hours_p90, analogue_event_ids, classifier_version. Keep capacity_impact_mw for backward compat.
Update extract_primary_event to populate new fields when classifier returns them.
Commit: frontier-D.4: structured event schema.
D.5 Historical analogue matching
backend/app/services/event_analogues.py with find_analogues(event, db, k=5) returning the 5 past events with highest cosine similarity on [event_type_one_hot, magnitude_mw, hour_of_day, day_of_week, regime_one_hot]. Surface in event detail UI.
Commit: frontier-D.5: historical event analogues.
D.6 Validation on golden set
Hand-curate a 50-article golden set in backend/tests/data/news_golden.jsonl. Test asserting fine-tuned scorer accuracy beats heuristic by ≥ 15 pp.
Commit: frontier-D.6: news scorer validation harness.
Phase D acceptance
Domain LLM scorer is the default in .env.example.
Structured event schema in place; analogues visible in UI.
Fine-tuned scorer beats heuristic on golden set.
Phase E — Real grid topology + DC-OPF for cross-zone trades
Goal. Model congestion between zones so the simulator prices basis trades correctly.

E.1 Topology ingest
backend/scripts/ingest_grid_topology.py pulling PJM Data Miner topology, ERCOT MIS topology, NYISO open-access tariff data, ENTSO-E cross-border capacities.
Output: backend/data/grid_topology.json plus new tables grid_node, grid_edge (Alembic migration — see F.1; if Alembic isn't set up yet, do a bare-bones migration here using Base.metadata extended).
Commit: frontier-E.1: grid topology ingest.
E.2 DC-OPF solver
backend/app/grid/dc_opf.py implementing vanilla DC optimal power flow (linear program; scipy.optimize.linprog or cvxpy — pick one and pin). Inputs: node loads, generation capacity, edge thermal limits. Outputs: line flows, locational marginal prices.
Tests: 3-bus textbook example with known LMPs.
Commit: frontier-E.2: DC-OPF solver.
E.3 Cross-zone basis trade type
Extend RiskAssessmentRequest with optional basis_against_market_code: str and basis_direction: "long" | "short". When set, simulator runs paired paths for both markets using the correlation matrix from C.1; pnl is the spread.
Tests: GB_POWER vs EPEX_DE basis trade returns sane numbers.
Commit: frontier-E.3: basis trade type.
E.4 Congestion-aware risk
DC-OPF run per simulated path on the topology produces a per-path congestion shock that maps into the price σ for nodes near a binding constraint. Risk simulator picks this up.
Commit: frontier-E.4: congestion-aware risk.
E.5 Topology UI
Frontend page /grid rendering the topology graph with current flow colours and basis-spread overlays.
Commit: frontier-E.5: grid topology UI.
Phase E acceptance
Basis trades quotable end-to-end.
DC-OPF runs in < 50ms for a 50-node sub-network.
Phase F — Enterprise hardening (absorbs PLAN Phase 9 + 10)
Goal. Auth, audit log, Postgres + Alembic, observability, exports, deployment-ready, SOC2 prep.

F.1 Postgres + Alembic
Replace SQLite by reading DATABASE_URL. Add psycopg[binary]. alembic init backend/alembic. Generate baseline migration from current models. Convert any partial migrations from earlier phases into proper Alembic revisions.
Stop calling Base.metadata.create_all in main.py.
Commit: frontier-F.1: postgres + alembic.
F.2 JWT auth
fastapi-users JWT backend. Wire the existing User model. Endpoints behind Depends(current_user). Per-user Decision/Position rows.
Tests: anon hits 401; authenticated hits 200; user A cannot read user B's decisions.
Commit: frontier-F.2: jwt auth.
F.3 Audit log
All API mutations write to audit_log(actor, action, target, before, after, signed_hash). Hash chain for tamper-evidence.
GET /api/audit?from=&to= for compliance export.
Commit: frontier-F.3: audit log.
F.4 PDF + Excel export
POST /api/risk-assessment/export?format=pdf|xlsx returning a downloadable file: timestamp, full coefficients, path-fan SVG, calibration record, FX provenance, scenarios. Use reportlab for PDF, openpyxl for XLSX.
Frontend "Export" button on the risk panel.
Commit: frontier-F.4: export pack.
F.5 OpenTelemetry observability
OTel instrumentation on FastAPI + SQLAlchemy + httpx. Console exporter by default; OTLP when OTEL_EXPORTER_OTLP_ENDPOINT set.
Structured JSON logs via structlog.
Commit: frontier-F.5: observability.
F.5.1 Rate limiting (PLAN Phase 10 finish)
slowapi middleware. 60 req/min per user on data endpoints; 10 req/min on /risk-assessment; 5 req/min on /risk-assessment/sensitivity.
Commit: frontier-F.5.1: rate limiting.
F.6 Docker Compose deployment
Update infrastructure/docker-compose.yml with Postgres + Redis + backend + frontend + OTel collector. make deploy brings the stack up cleanly on a fresh Linux box.
Commit: frontier-F.6: deployment compose.
F.6.1 Background workers (PLAN Phase 9 finish)
Move _refresh_all_markets, the nightly backtest job, and the hourly P&L-fill job out of BackgroundScheduler into arq (Redis-backed). Workers run as a separate process in Compose. Retries with exponential backoff.
Commit: frontier-F.6.1: background workers.
F.7 WebSocket push (PLAN Phase 8 finish)
backend/app/api/ws.py exposing /ws/markets/{code} pushing price_tick, forecast_revision, new_event, alert, risk_recomputed JSON messages. Source from a Redis pub/sub populated by the workers above.
Frontend lib/use-market-stream.ts hook applying ticks to KLineCharts via updateData.
Commit: frontier-F.7: websocket push.
F.8 SOC2 prep documentation
docs/SOC2.md covering audit log, encryption at rest + transit, secret management, access control, change management (Alembic migrations), incident response stub, vendor list.
Commit: frontier-F.8: SOC2 prep docs.
Phase F acceptance
App runs in Docker Compose with Postgres + Redis + OTel.
All requests authenticated; mutations audit-logged.
Export pack works end-to-end.
WebSocket push delivers ticks to a connected browser.
What's deliberately not in this roadmap
A separate "alerts UI overhaul" beyond what frontend/components/alerts-panel.tsx already does. Wired; richer alerts can come post-F.
A trade-execution / OMS layer (booking actual trades into a broker). Out of scope.
Mobile UI. Out of scope.
Progress log (append-only)
Format: YYYY-MM-DD frontier-X.N (sha) — one-line result. Tests: pass/fail. Notes.

2026-05-10 frontier-A.1 (pending) — Position-sizing solver endpoint and risk-first panel mode shipped. Tests: pass. Notes: backend pytest 44 passed; frontend tsc clean; ESLint hung locally with no diagnostics.
2026-05-10 frontier-A.2 (pending) — Sensitivity endpoint and workbench heatmap shipped. Tests: pass. Notes: backend pytest 46 passed; frontend tsc clean.
2026-05-10 frontier-A.3 (pending) — Calibration logging, P&L fill, API badge payload, and workbench badge shipped. Tests: pass. Notes: backend pytest 50 passed; frontend tsc clean.
2026-05-10 frontier-A.4 (pending) — Decision diary create/list endpoints, save modal, maturity update, and workbench panel shipped. Tests: pass. Notes: backend pytest 51 passed; frontend tsc clean.
2026-05-10 frontier-A.5 (pending) — Path-fan endpoint and SVG workbench visualization shipped. Tests: pass. Notes: backend pytest 52 passed; frontend tsc clean.
2026-05-10 frontier-A.6 (pending) — KLineCharts workbench wrapper, fundamentals timeseries API, and wind/solar/event overlays shipped. Tests: pass. Notes: backend pytest 53 passed; frontend tsc clean.
2026-05-10 frontier-A.7 (pending) — Persisted resizable workbench layout with chart/risk top row and news/events/calibration/diary bottom row shipped. Tests: pass. Notes: backend pytest 53 passed; frontend tsc clean; local Next dev/build smoke blocked by stale hanging Next processes.
2026-05-10 frontier-B.1 (pending) — Regime classifier extracted, per-regime residual sigma trained and persisted into forecast snapshots. Tests: pass. Notes: focused backend 10 passed; full backend pytest 56 passed; frontend tsc clean.
2026-05-10 frontier-B.2 (pending) — Forecaster registry, active forecaster setting, cache separation, and naive 24h persistence forecaster shipped. Tests: pass. Notes: focused backend 5 passed; full backend pytest 58 passed; frontend tsc clean.
2026-05-10 frontier-B.3 (pending) — Chronos-Bolt forecaster adapter, dependency/config docs, and mocked distribution test shipped. Tests: pass. Notes: focused backend 6 passed; full backend pytest 59 passed; frontend tsc clean.
2026-05-10 frontier-B.4 (pending) — Multi-forecaster walk-forward backtest and CLI comparison flag shipped. Tests: pass. Notes: focused backend 5 passed; full backend pytest 60 passed; frontend tsc clean.
2026-05-10 frontier-B.5 (pending) — LLM coefficient ablation service, Kupiec POF test, CLI report writer, and synthetic calibration test shipped. Tests: pass. Notes: focused backend 2 passed; full backend pytest 62 passed; frontend tsc clean.
2026-05-10 frontier-B.6 (pending) — Jinja2 single-file report renderer, inline PIT SVG, sample render test, and GB_POWER HTML artifact shipped. Tests: pass. Notes: focused backend 1 passed; full backend pytest 63 passed; frontend tsc clean.
2026-05-10 frontier-B.7 (pending) — Latest backtest API endpoint, dashboard backtest metrics, and frontend backtest strip shipped. Tests: pass. Notes: focused backend 9 passed; full backend pytest 64 passed; frontend tsc clean.
2026-05-10 frontier-B.acceptance (pending) — GB_POWER gbr-vs-chronos backtest and GB_POWER ablation reports generated; calibration status honest for EPEX_DE; SQLite risk-log compatibility bridge added. Tests: pass. Notes: full backend pytest 65 passed; frontend tsc clean.
2026-05-10 frontier-C.1 (pending) — Six-hour cached cross-market hourly-return correlation matrix shipped. Tests: pass. Notes: GB_POWER vs ERCOT_NORTH finite/non-zero; full backend pytest 66 passed; frontend tsc clean.
2026-05-10 frontier-C.2 (pending) — Portfolio-risk endpoint with correlated Monte Carlo aggregation and per-position contributions shipped. Tests: pass. Notes: anti-correlated pure test plus endpoint passed; full backend pytest 68 passed; frontend tsc clean.
2026-05-10 frontier-C.3 (pending) — Deep hedging MLP, training script, trained policy artifact, and optimal-hedge endpoint shipped. Tests: pass. Notes: trained policy beat random hedge on held-out scenarios; full backend pytest 70 passed; frontend tsc clean.
2026-05-10 frontier-C.4 (pending) — Risk panel hedge suggestion UI wired to optimal-hedge endpoint. Tests: pass. Notes: optimal-hedge endpoint smoke passed; frontend tsc clean.

Blockers (agent appends; user resolves)
Format: YYYY-MM-DD frontier-X.N — short description. To unblock: …

(empty)
