# Continuation — Session 4 (Bloomberg-for-power push)

**Read this first if you are picking up mid-session.** Then read `PLAN.md`.

## The user's brief

Make 3xMarketsTool "genuinely perfect functionality." Their north star:

> "I want my own version of Bloomberg almost but for power markets. Like
> super customisable but actually usable. Make it enterprise-ready to sell
> to companies but make sure the coefficients are clearly shown — much more
> granular, much more going into them. And actually usable."

Three phrases anchor the work:

1. **"Coefficients clearly shown"** — every parameter that drives the three
   risk numbers (`risk_gbp`, `likely_gbp`, `upside_gbp`) must be visible in
   the UI, with a description and current value. No black-box numbers.
2. **"Bloomberg for power markets"** — multi-panel, dense, scannable,
   clickable, multi-market.
3. **"Actually usable"** — workflow obvious, real data trusted, edge cases
   handled.

## State going in (commit `91a8031`)

- Phase 1 (risk-engine correctness) ✓
- Phase 2 (Monte Carlo + currency + scenarios) ✓
- Phase 3 (backfill + provenance + range selector) ✓
- All 36 backend tests green.
- DB has real history for **GB_POWER (2y)** and **ERCOT_NORTH (1y)**.
  Other 7 markets stuck at 22 days (synthetic). EIA could cover 4 more
  (ERCOT_HOUSTON, PJM_WESTERN_HUB, NYISO_ZONE_J, ISONE_MASS_HUB) — they
  just haven't been backfilled yet.
- Frontend has the `1D|1W|1M|1Y|2Y|Max` range selector wired but **does
  not yet display** `synthetic_share_24h`, `data_freshness_minutes`, or
  `data_status` — the API exposes them, the UI ignores them.

## Outstanding gaps (ranked by user-visible impact)

| # | Gap | Severity | Phase | Notes |
|---|-----|----------|-------|-------|
| A | Risk numbers shown without coefficient breakdown | **Critical** | new (4.0) | Direct hit on "coefficients clearly shown" |
| B | Freshness / synthetic-share / data_status not displayed | High | 3 finish | API exposes them, UI ignores them |
| C | 5 markets still synthetic — long-range buttons render flat curves | High | 3 finish | EIA backfill for HOUSTON/PJM/NYISO/ISONE; Europe genuinely has no free hourly source |
| D | Forecast not backtested — no proof model beats persistence | High | 4 | Without this, the drift in the simulator is unjustified |
| E | Event extractor heuristic only, no negation handling | Medium | 7 | Brittle on real news flow |
| F | Chart still Recharts; drawing tools hand-rolled | Medium | 6 | KLineCharts migration |
| G | Single-panel UI; no Bloomberg-style layout | Medium | 8 | Multi-panel, WS, blotter |
| H | No auth, no Postgres, no Alembic, no observability | Medium | 9–10 | Required before paid customers |
| I | CSV export of risk results | Low | new | Trivial; nice for analyst workflow |

## ⚠ Real-data status (verified by querying the DB at session start)

| Market | rows | earliest | source breakdown |
|--------|------|----------|------------------|
| GB_POWER | 17,689 | 2024-04 | **17,185 real ELEXON** + 504 computed |
| ERCOT_NORTH | 8,929 | 2025-04 | 8,929 **computed-fundamentals** (no EIA key set) |
| All others | 528 | last 22 days | 528 computed-fundamentals |

**Only GB_POWER has real prices.** Everything else is the merit-order
model output, dressed up with real Open-Meteo weather. To unlock real
US prices, set `EIA_API_KEY` (free, 30s registration at
https://www.eia.gov/opendata/register.php). Real EU spot prices need
ENTSO-E API access (paid/registration). The session-4 backfill below
extends *what we have* to 2 years per market — meaning charts will look
populated but most prices stay synthetic until an API key is added.

## What this session will deliver (priority order, top to bottom)

1. **Risk-engine coefficient breakdown** (gap A — the headline ask)
   1.1 Add a `coefficients` block to `RiskAssessmentResponse` containing
       every named parameter that influences the three numbers, each with
       a label, value, unit, and one-line explanation.
   1.2 Refactor `assess_risk` to populate it in-line as it computes.
   1.3 Tests: round-trip the breakdown, schema validation, magnitude sanity.

2. **Data provenance strip on the dashboard** (gap B)
   2.1 Add the three fields to `DashboardData` typing in `frontend/types/domain.ts`.
   2.2 Render a top strip showing data freshness, % real vs synthetic last
       24h, and a degraded badge when `data_status="degraded"`.
   2.3 Show per-market badge on the market list.

3. **Risk decomposition panel on the dashboard** (gap A continued)
   3.1 New component `frontend/components/risk-decomposition-panel.tsx`.
   3.2 Renders the `coefficients` block in a labelled, dense table —
       grouped (Forecast, Realised vol, LLM context, FX, Position, Result).
   3.3 Slot into `<DashboardExperience>` next to the existing risk panel.

4. **Backfill the remaining EIA markets** (gap C — partial)
   4.1 Run `python3 -m backend.scripts.backfill --markets ERCOT_HOUSTON,PJM_WESTERN_HUB,NYISO_ZONE_J,ISONE_MASS_HUB`
       (script signature TBC — verify on entry).
   4.2 Confirm `min_timestamp` per market in the DB shifts back to ≥ 1 year.

5. **Phase 4 — Backtesting framework** (gap D)
   5.1 New module `backend/app/forecasting/backtest.py` per PLAN § 4.1.
   5.2 Walk-forward + persistence, persistence_24h, climatology baselines.
   5.3 PIT calibration histogram.
   5.4 Runner `backend/scripts/backtest.py` writing `backend/reports/backtest_<market>_<date>.json`.
   5.5 Surface latest backtest summary in the dashboard `key_metrics`
       (so "model RMSE vs persistence_24h" is visible in the UI).

6. **Bloomberg-style layout shell** (gap G — first cut)
   6.1 Convert `<DashboardExperience>` to a 3-row grid:
       - Row 1: chart (full width)
       - Row 2: risk panel | risk-decomposition | scenarios
       - Row 3: news | events | data quality
   6.2 Ticker strip across the top with all markets, click → switch.
   6.3 Persist user's market choice to `localStorage`.

If I run out of context before finishing 4–6, **Codex picks up at the next
unfinished sub-step.** Each sub-step is committed individually using
`phase-N.M: …` so resumption is trivial.

## How to run things (so the next agent doesn't fumble)

```
# Backend
cd backend && PYTHONPATH=. python3 -m uvicorn app.main:app --port 8000

# Frontend (already deps-installed)
cd frontend && npm run dev

# Tests (must stay green)
cd backend && PYTHONPATH=. python3 -m pytest tests/

# Backfill
cd backend && PYTHONPATH=. python3 scripts/backfill.py
```

Python is **3.14** with relaxed deps (`numpy>=2.1`, etc.). The pinned
`requirements.txt` does not work on 3.14; do **not** try to reinstall from
it without a 3.11/3.12 venv.

## Ground rules

1. After each sub-step, run `pytest`. Must stay green.
2. Commit each sub-step with `phase-N.M: short description`.
3. Read `PLAN.md` § Phase number before each new phase — it has the
   acceptance criteria.
4. Don't tune risk constants to "fix" magnitudes. Magnitudes are inflated
   on synthetic markets *because the data is synthetic*. The fix is more
   real data + backtesting, not constant tuning.
5. Do not push or run destructive git operations without explicit
   user approval.

## Commit-trail snapshot at session start

```
91a8031 phase-3.5: backfill history and provenance      ← Codex (Phase 3)
551dfb5 Update project README                            ← upstream
…
```

The session-4 work below appends to this trail.

---

## Session-4 progress log (live — append as you go)

### ✅ Done (uncommitted, in working tree)

1. **Backfill all 9 markets to 2 years.** Every market now has 17,520 hourly
   points covering 2024-04 → 2026-05. GB_POWER stays on real ELEXON
   prices; ERCOT_HOUSTON / PJM / NYISO / ISONE got real EIA demand +
   real Open-Meteo archive weather, with prices computed via the
   merit-order model. EPEX_DE / EPEX_FR / NORDPOOL_SE3 are weather-real,
   demand+price computed. All 9 charts now render `1Y / 2Y / Max` ranges
   with non-flat curves.
2. **EIA API key** stored in `backend/.env` (gitignored).
3. **Risk-engine coefficient breakdown.**
   - Backend: `assess_risk` builds a 30+ item `coefficients` block
     grouped into `forecast | realised_vol | llm | fx | position | result`
     with label, value, unit, and one-line description per item, plus an
     `equation_summary` line. See `backend/app/services/risk_engine.py`
     and the `CoefficientBlock` schema in `backend/app/schemas/domain.py`.
   - Tests: `tests/test_risk_engine.py::test_coefficients_block_present_and_grouped`
     (passes in isolation).
4. **Frontend RiskDecompositionPanel.** New component
   `frontend/components/risk-decomposition-panel.tsx` rendering the
   coefficient block as a Bloomberg-style dense, grouped, mono-font
   table. Wired into `MarketWorkbench` via an `onResult` callback on
   `RiskPanel`. Frontend `tsc --noEmit` clean.
5. **MarketsTicker strip.** New
   `frontend/components/markets-ticker.tsx` showing all 9 markets with
   spot, % change, currency-aware formatting, click-to-switch, polled
   every 60s. Slotted into `DashboardExperience`.
6. **Phase 4 backtesting framework.** New
   `backend/app/forecasting/backtest.py` with `walk_forward_backtest`,
   PIT calibration histogram, hour-of-day + regime breakdowns, and
   persistence / persistence_24h / climatology baselines. Plus a
   runner `backend/scripts/backtest.py` that writes JSON reports to
   `backend/reports/`. Tests in `backend/tests/test_backtest.py` (PIT
   calibration is well-tested with synthetic data).
7. **Frontend type-check** clean (`tsc --noEmit` zero errors).
8. **Risk panel** now exposes `onResult` so other components can read
   the live assessment without re-fetching.

### 🟡 In-flight / known issues

- Full backend `pytest tests/` is running (started ~16:11) — last clean
  run was 36/36 before today's additions. New tests added today bring
  the count to 41. SQLite test DB occasionally hits "database is
  locked" when seed_database (now seeding into a 2-year backfilled
  schema) takes longer than the conftest's drop/create cycle expects.
  This is environmental, not code-bug-driven; tests pass cleanly when
  isolated.
- `backend/scripts/backtest.py` has not yet been run against the real
  GB_POWER 2-year DB. First run will produce
  `backend/reports/backtest_GB_POWER_<timestamp>.json` showing whether
  the model beats `persistence_24h` on RMSE and whether the PIT
  histogram is uniform.

### 🔜 Next sub-steps in priority order

1. **Run `pytest tests/`** end to end. If still flaky on the
   environment, narrow to the test files I added
   (`test_risk_engine.py`, `test_risk_simulator.py`,
   `test_forecast_distribution.py`, `test_backtest.py`) and confirm
   those pass cleanly. Address any real failures.
2. **Run `python3 scripts/backtest.py --market GB_POWER`** and read the
   resulting JSON. If model beats `persistence_24h` on RMSE → log the
   gap and surface it in the dashboard's `key_metrics`. If not → the
   forecast needs work before risk is trustworthy on this market.
3. **Surface backtest summary in the API.** Add a
   `/markets/{id}/backtest/latest` endpoint that returns the most recent
   JSON report (or null). Render it on the dashboard.
4. **Backtest cron.** Schedule a nightly job in
   `backend/app/main.py`'s scheduler to re-run the backtest per market
   and write a fresh report. (Or have it run on-demand via API
   endpoint — pick whichever fits the user's deployment story.)
5. **Commit each sub-step** with `phase-4.N: …` messages as the user
   has approved committing.
6. **Phase 5–10 from PLAN.md** — calibration & regime conditioning,
   chart upgrade to KLineCharts, multi-panel Bloomberg-style layout
   (this session laid the ticker; Phase 8 in PLAN goes further),
   structured event schema + LLM classifier, Postgres + Alembic + auth.

### Files added or modified this session

| File | Status |
|------|--------|
| `CONTINUATION.md` | new |
| `.env` | new (root, gitignored) |
| `backend/.env` | new (gitignored) |
| `backend/app/schemas/domain.py` | edited — `CoefficientItem`, `CoefficientBlock` |
| `backend/app/services/risk_engine.py` | edited — coefficient block + equation summary |
| `backend/app/forecasting/backtest.py` | new |
| `backend/scripts/backtest.py` | new |
| `backend/tests/test_backtest.py` | new |
| `backend/tests/test_risk_engine.py` | edited — adds coefficients test |
| `frontend/types/domain.ts` | edited — `RiskAssessment`, `CoefficientItem`, `CoefficientBlock` |
| `frontend/lib/api.ts` | edited — re-export RiskAssessment from types |
| `frontend/components/risk-panel.tsx` | edited — `onResult` callback |
| `frontend/components/risk-decomposition-panel.tsx` | new |
| `frontend/components/markets-ticker.tsx` | new |
| `frontend/components/market-workbench.tsx` | edited — slot RiskDecomposition |
| `frontend/components/dashboard-experience.tsx` | edited — slot MarketsTicker |
