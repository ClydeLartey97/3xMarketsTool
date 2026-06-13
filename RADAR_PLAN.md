# Phase G — The Radar (proactive push) + repo cleanup

This is a **resumable build log**. It is written so that work can stop at any point and
be picked up cold by reading this file alone. Do the steps **strictly top to bottom**.
Every step is atomic, ends with a concrete **VERIFY** gate, and maps to **one commit**
titled `radar-G.N: short description` (cleanup commits use `cleanup-0.N`).

> Style rule for all code, comments, and commit messages in this phase: product voice
> only. No references to assistants, models, or who/what wrote the code. Match the tone
> of the existing `frontier-*` log in `FRONTIER.md`.

---

## ▶ RESUME HERE

```
NEXT STEP: G.acceptance  (G.1–G.9 committed; only the live browser run remains)
```

Note: the two foundational service tests (ranking/determinism + failure isolation)
were brought forward into G.1 as its verification gate. G.9 still owns the
book-aware test and the endpoint test. Also: `radar_service` lazy-imports
`risk_engine` inside `_assess` (module stays light; mirrors the route handlers).

Update this block after every commit: set `NEXT STEP` to the first unchecked item and
add a one-line entry to the **Progress log** at the bottom. That is the single source of
truth for "where did we get to."

---

## What the Radar is (one paragraph, so a cold reader gets it)

Today the product is pull-based: a trader types a position into the workbench and gets the
three numbers (`risk_gbp / likely_gbp / upside_gbp`). The Radar flips that to push. A
background job continuously runs the existing risk engine across **all 9 markets** at a
standardised unit position **and** against the signed-in user's open blotter book, ranks
each market by a composite of *edge*, *imminent catalyst proximity*, and *calibration
confidence*, and serves the ranked result as **Opportunities** and **Threats**. The UI
surfaces this as a dedicated `/radar` page (and later a homepage strip) that updates live
over the existing WebSocket. It introduces almost no new math — it is an assembly of
`assess_risk`, `risk_calibration_for_market`, the events table, and the blotter.

### MVP boundary (what is in this plan vs deferred)

IN (this plan):
- Per-market standardised scan (long + short), composite ranking, opportunity/threat split.
- Book-aware threats from the user's open `is_open` decisions.
- Redis-cached snapshot refreshed by an `arq` cron job; on-demand compute fallback.
- `GET /api/radar` endpoint, `radar-panel.tsx`, `/radar` route + nav entry.
- Live refetch on a `radar_updated` stream message; interval poll as the floor.
- Unit/integration tests + degradation behaviour.

DEFERRED (explicitly not now — note them, don't build them):
- Per-user push notifications / email.
- Auto-suggested hedges inside Radar cards (the data is there; the UX is a later step).
- Multi-horizon radar (only one horizon in MVP).
- Personalised scoring weights.

---

## Grounding facts (verified against the codebase — trust these, but re-confirm if stale)

- **Engine entrypoint:** `assess_risk(db: Session, inputs: RiskInputs) -> dict[str, Any]`
  in `backend/app/services/risk_engine.py`. `RiskInputs` is a dataclass; key fields:
  `market_code, position_gbp, horizon_hours, target_timestamp, direction ("long"|"short"),
  position_unit ("GBP"|"MWh"), hedge_ratio, n_paths, random_seed, scenarios`.
- **Engine return dict already contains everything Radar needs to rank:**
  `risk_gbp, likely_gbp, upside_gbp, edge_score, confidence, regime, catalyst_severity,
  asymmetry, tail_multiplier, prob_loss, decision_gate, spot_price, forecast_price`.
  → Radar does **not** need to recompute edge; reuse `edge_score`.
- **Calibration status:** `risk_calibration_for_market(db, market_id, ...)` in
  `backend/app/services/risk_calibration.py` returns a dict with
  `calibration_status: "honest" | "understating" | "overstating"` (key at line ~164).
- **Markets:** `select(Market).order_by(Market.code.asc())` — there are 9. See the loop in
  `backend/app/workers/jobs.py:refresh_all_markets`.
- **Open positions (blotter):** `list_decisions(db, market_id=None, user_id=...)` in
  `backend/app/services/decision_diary.py` returns dicts with `is_open`, `market_code`,
  `position_gbp`, `direction`, `horizon_hours`, `closed_at`.
- **Events for catalyst proximity:** `Event` model (see `backend/app/models`); events carry
  severity + an expected timestamp. Confirm the exact column name when implementing
  (`grep -n "class Event" backend/app/models/entities.py`). Use the same source the
  workbench/event-feed uses so "imminent" matches what the user already sees.
- **Stream publish:** `publish_market_message_sync(market_code, {"type": ..., ...})` in
  `backend/app/services/market_stream.py`. A pseudo-market code `"ALL"` is already used for
  global messages (`fill_risk_assessment_pnl` publishes `{"type":"risk_recomputed"}` to
  `"ALL"`). Channel = `market-stream:{CODE}` via `market_stream_channel`.
- **WebSocket bridge:** `backend/app/api/ws.py` → `/ws/markets/{code}` relays the pub/sub
  channel verbatim to the browser. Frontend hook: `frontend/lib/use-market-stream.ts`.
- **Worker:** cron jobs live in `backend/app/workers/worker.py:WorkerSettings.cron_jobs`;
  the callables they wrap live in `backend/app/workers/jobs.py`. Retry/backoff helper
  `_run_with_retry` already exists in `worker.py`.
- **API base + auth (frontend):** `frontend/lib/api.ts`. Public base is `/api/backend`
  (proxied). Server-side auto-login handles the bearer token; new fetchers follow the same
  pattern as `fetchDashboard`/`fetchMarketsOverview` already in that file.
- **Schemas:** Pydantic response models live in `backend/app/schemas/domain.py`
  (e.g. `MarketOverviewItem` at ~531). Add Radar models there.
- **Routes:** `backend/app/api/routes.py` (1,234 lines, single router `router`). Rate-limit
  decorators: `@limiter.limit(...)` with `DATA_LIMIT` / `RISK_ASSESSMENT_LIMIT` /
  `SENSITIVITY_LIMIT` constants already defined near the top.
- **Nav:** `frontend/components/app-shell.tsx` → `navItems` array.

---

# Phase 0 — Housekeeping (do first; cheap, safe, unblocks everything)

All targets below are **untracked or gitignored** — confirmed via `git ls-files`. Deleting
them changes nothing in git history and breaks no imports (the ` 2` files are not imported
anywhere). Still, run the VERIFY gate after.

### 0.1 — Delete the 150 ` 2` duplicate files
- **What:** every file whose name contains a literal ` 2.` (space-two-dot) suffix —
  `__init__ 2.py`, `routes 2.py`, `Makefile 2`, etc. They are accidental bulk-copy
  artifacts, untracked, imported by nothing.
- **How (exact):**
  ```bash
  cd "/Users/clydelartey/Documents/Code/Market Speculation"
  # Dry run — eyeball the list first:
  find . -type f -name "* 2.*" -not -path '*/node_modules/*' -not -path '*/.next*' -not -path '*/.git/*'
  # Also catch extensionless dups like "Makefile 2":
  find . -type f -name "* 2" -not -path '*/node_modules/*' -not -path '*/.next*' -not -path '*/.git/*'
  # Delete (run only after the lists look right):
  find . -type f \( -name "* 2.*" -o -name "* 2" \) -not -path '*/node_modules/*' -not -path '*/.next*' -not -path '*/.git/*' -delete
  ```
- **Also:** remove the stray `__pycache__/* 2.pyc` entries (covered by the glob above).
- **VERIFY:** `find . -name "* 2.*" -not -path '*/node_modules/*' -not -path '*/.git/*' | wc -l`
  prints `0`. Then `cd backend && python -c "import app.main"` still imports clean, and
  `cd frontend && npm run build` (or `tsc --noEmit`) still passes.
- **Commit:** `cleanup-0.1: remove accidental " 2" duplicate files`

### 0.2 — Delete dead build artifacts (DBs KEPT — see correction)
- **CORRECTION (applied):** the root `threex.db` / `test_threex.db` are NOT stray junk.
  `backend/.env` sets `DATABASE_URL=sqlite:///./threex.db`, so `threex.db` (3 MB) is the
  **active dev database** and `test_threex.db` is the test DB. Both are already gitignored,
  so they don't pollute git. Deleting them would wipe seeded local data for no benefit.
  → **Kept both.** Only the dead build dir was removed.
- **What was done:** `rm -rf "frontend/.next_broken_1780232986"` (gitignored dead build,
  32K). DB files left in place.
- **VERIFY:** no `.next_broken_*` dirs remain; `threex.db` + `test_threex.db` still present.
- **Commit:** `cleanup-0.2: remove dead next build artifact`

### 0.3 — Confirm `.gitignore` covers the classes above (prevent recurrence)
- **What:** ensure `*.db`, `frontend/.next_broken_*/` already present (they are). Add a
  guard line for the dup pattern so it never gets committed: append `*\ 2.*` and `*\ 2`
  patterns under a `# accidental copies` comment **only if** they are not already ignored.
- **VERIFY:** create a throwaway `foo 2.py`, run `git status`, confirm it is ignored, delete it.
- **Commit:** `cleanup-0.3: gitignore accidental-copy filename patterns`

### 0.4 — Retire the superseded chart component (REVERTED — was a mistake)
- **OUTCOME: deletion reverted.** `price-chart.tsx` is the ACTIVE KLineCharts implementation:
  it exports `PriceChart` + the chart types (`ChartHistoryPoint`/`ChartForecastPoint`/
  `RiskOverlay`), and `kline-price-chart.tsx` is a thin wrapper that imports them. It was NOT
  dead code. The detection grep used `grep -v "kline-price-chart"`, which excluded the one
  file that imports `price-chart` — hiding the dependency. The deletion broke the frontend
  typecheck (`TS2307` in `kline-price-chart.tsx`), caught at the G.5 typecheck gate, and was
  restored verbatim from history (commit 11b6e10).
- **Lessons for future cleanup:** never exclude the sibling/wrapper file when grepping for
  references; and run `tsc --noEmit` as part of any frontend deletion's VERIFY, not just at
  feature time.
- **Also wrong in the earlier note:** there are not "two redundant charts" — `price-chart.tsx`
  (impl) and `kline-price-chart.tsx` (data-fetching wrapper) are both live and complementary.
  `recharts` genuinely is not a dependency; that part stands.
- **How (exact, do NOT delete blind):**
  ```bash
  grep -rn "price-chart" frontend/app frontend/components frontend/lib --include=*.tsx --include=*.ts | grep -v "kline-price-chart"
  ```
  - If that returns **nothing**: delete `price-chart.tsx`, and if `recharts` is now unused
    (`grep -rn "recharts" frontend/{app,components,lib}`), remove it from
    `frontend/package.json` deps and run `npm install` to update the lockfile.
  - If it returns references: **stop**, leave the file, note the references here as a blocker.
- **VERIFY:** `npm run build` passes; no `recharts` import errors.
- **Commit:** `cleanup-0.4: retire legacy recharts price chart` (skip if still referenced)

> Note: `routes.py` (1,234 lines) splitting into domain routers is a worthwhile cleanup but
> is **deferred** — it touches every endpoint and risks merge pain mid-feature. Do it only
> after Phase G lands. Recorded here so it isn't forgotten.

---

# Phase G — The Radar

Architecture at a glance (data flow):

```
arq cron (every refresh cycle)
   └─ compute_radar_snapshot()           [jobs.py]
        └─ compute_radar(db, user_id)     [services/radar_service.py]
             ├─ for each Market: assess_risk(long) + assess_risk(short)
             ├─ risk_calibration_for_market() → confidence gate
             ├─ Event lookup → catalyst proximity (hours-to-maturity, severity)
             └─ list_decisions(is_open) → book-aware threats
        └─ write snapshot → Redis (radar:latest:<scope>)   [radar_cache]
        └─ publish_market_message_sync("ALL", {"type":"radar_updated"})

GET /api/radar  [routes.py]
   └─ read Redis snapshot (or compute on demand if empty) → RadarResponse

Frontend
   /radar page → radar-panel.tsx → fetchRadar() [api.ts]
        └─ use-market-stream("ALL") → on "radar_updated" → refetch
        └─ interval poll (floor) every settings.data_refresh_interval
```

### G.1 — `radar_service.py`: the pure scan + rank
- **File:** `backend/app/services/radar_service.py` (new).
- **Public API:**
  ```python
  from dataclasses import dataclass

  RADAR_UNIT_POSITION_GBP = 100_000  # standardised notional for cross-market comparison
  RADAR_DEFAULT_HORIZON_H = 24
  RADAR_SCAN_N_PATHS = 2_000          # lighter than the 5_000 interactive default; this is a sweep

  @dataclass
  class RadarItem:
      market_code: str
      market_name: str
      direction: str            # the better-edge side chosen for this market
      risk_gbp: float
      likely_gbp: float
      upside_gbp: float
      edge_score: float         # reused verbatim from assess_risk
      confidence: float
      regime: str
      catalyst_severity: float
      calibration_status: str   # "honest" | "understating" | "overstating" | "unknown"
      hours_to_catalyst: float | None
      radar_score: float        # composite used for ranking (see below)
      kind: str                 # "opportunity" | "threat"
      reason: str               # short human string, e.g. "wind-drop catalyst in 14h"

  def compute_radar(
      db: Session,
      *,
      user_id: int | None = None,
      horizon_hours: int = RADAR_DEFAULT_HORIZON_H,
      unit_position_gbp: float = RADAR_UNIT_POSITION_GBP,
  ) -> dict[str, Any]:
      """Scan all markets, return {generated_at, horizon_hours, universe_count,
      opportunities: list[RadarItem-as-dict], threats: list[RadarItem-as-dict]}."""
  ```
- **Algorithm (explicit):**
  1. Load markets: `db.scalars(select(Market).order_by(Market.code.asc())).all()`.
  2. For each market, **inside its own `try/except`** (mirror `refresh_all_markets` — one bad
     market must not sink the scan; on failure append to a `failed` list and continue):
     - Run `assess_risk` twice, `direction="long"` and `direction="short"`, with
       `position_gbp=unit_position_gbp`, `horizon_hours=horizon_hours`,
       `n_paths=RADAR_SCAN_N_PATHS`, `random_seed=<fixed per market>` (determinism — e.g.
       `seed = abs(hash(market.code)) % 2**31`), `target_timestamp=None`.
     - Pick the side with the higher `edge_score` as the market's representative `RadarItem`.
     - `calibration_status` ← `risk_calibration_for_market(db, market.id)["calibration_status"]`
       (wrap in try/except → `"unknown"`).
     - Catalyst proximity ← query `Event` rows for this market whose expected timestamp is in
       `[now, now + horizon_hours]`; take the highest-severity one; compute
       `hours_to_catalyst` and a one-line `reason`. (Confirm Event columns first.)
  3. **Composite `radar_score`** (keep it simple + explainable — it must be defensible in the
     glass-box spirit; document the formula in a docstring):
     ```
     base      = edge_score                                   # already risk-normalised
     cal_gate  = 1.0 if status == "honest"
                 else 0.6 if status in {"understating","unknown"}
                 else 0.3          # "overstating" → distrust, discount hard
     catalyst  = 0.0 if hours_to_catalyst is None
                 else (catalyst_severity * (1 - hours_to_catalyst / horizon_hours))
     radar_score = base * cal_gate + 0.5 * catalyst
     ```
  4. **Split:** an item is an `"opportunity"` if `likely_gbp > 0` and `radar_score > 0` and
     `decision_gate` is not a hard block; otherwise it is a candidate `"threat"`.
  5. **Book-aware threats:** load open positions via
     `list_decisions(db, user_id=user_id)` filtered to `is_open is True`. For each, re-run
     `assess_risk` at the *actual* position size/direction; if `risk_gbp` exceeds the
     position's stored risk by a margin, or a high-severity catalyst matures within horizon,
     emit a `threat` item with `reason` explaining the exposure. De-dupe by market_code
     (a book threat overrides a generic one for the same market).
  6. Sort `opportunities` by `radar_score` desc, `threats` by `radar_score` desc (threats use
     the same score but represent downside/exposure). Return top 8 of each (cap configurable).
- **Determinism + cost:** fixed seeds + `RADAR_SCAN_N_PATHS=2000` keep a full 9-market ×2
  scan well under a couple seconds. This runs in the worker, not the request path.
- **VERIFY:** `python -c "from app.db.session import SessionLocal; from app.services.radar_service import compute_radar; db=SessionLocal();
  import json; print(json.dumps(compute_radar(db), default=str)[:1500])"` prints a populated
  `opportunities`/`threats` structure against the dev DB without raising.
- **Commit:** `radar-G.1: cross-market scan + composite ranking service`

### G.2 — Snapshot cache
- **File:** add to `backend/app/services/radar_service.py` (or a small `radar_cache` section).
- **What:** read/write the latest snapshot to Redis with a TTL, with an in-process dict
  fallback when Redis is unreachable (dev without Redis must still work).
- **Exact:**
  ```python
  RADAR_CACHE_KEY = "radar:latest"          # global (anonymous) scope
  RADAR_CACHE_USER_KEY = "radar:latest:user:{user_id}"
  RADAR_CACHE_TTL_S = 15 * 60

  def cache_radar_snapshot(snapshot: dict, *, user_id: int | None = None) -> None: ...
  def read_radar_snapshot(*, user_id: int | None = None) -> dict | None: ...
  ```
  Use `redis.Redis.from_url(settings.redis_url, decode_responses=True)` exactly like
  `market_stream.publish_market_message_sync` does; swallow connection errors and fall back
  to a module-level `_MEMORY_SNAPSHOT` dict so the endpoint degrades gracefully.
- **VERIFY:** unit test round-trips a snapshot through `cache_radar_snapshot` /
  `read_radar_snapshot` with Redis down (monkeypatch the client to raise) and confirms the
  memory fallback returns it.
- **Commit:** `radar-G.2: redis-backed radar snapshot cache with memory fallback`

### G.3 — Worker job + cron
- **Files:** `backend/app/workers/jobs.py` (+ `worker.py`).
- **jobs.py — add:**
  ```python
  def compute_radar_snapshot() -> dict[str, Any]:
      from app.services.radar_service import compute_radar, cache_radar_snapshot
      require_database_schema(engine)
      with SessionLocal() as db:
          snapshot = compute_radar(db)              # global scope (no user) in the worker
      cache_radar_snapshot(snapshot)
      publish_market_message_sync("ALL", {"type": "radar_updated",
          "generated_at": snapshot["generated_at"]})
      return {"opportunities": len(snapshot["opportunities"]),
              "threats": len(snapshot["threats"]),
              "completed_at": datetime.now(timezone.utc).isoformat()}
  ```
  (Book-aware/per-user snapshots are computed on demand in the endpoint, not by the worker —
  the worker only maintains the global scope.)
- **worker.py — add:** import `compute_radar_snapshot`; wrap as
  `compute_radar_job(ctx)` via `_run_with_retry(ctx, "radar_snapshot", compute_radar_snapshot)`;
  add to `WorkerSettings.functions`; add a `cron(...)` entry that runs on the same minute
  cadence as `market_refresh` but offset by `second=30` (so it runs just after a refresh, on
  fresh data). `timeout=10 * 60`, `max_tries=3`.
- **VERIFY:** `arq app.workers.worker.WorkerSettings --check` (or start the worker locally with
  Redis up) logs a successful `radar_snapshot` run; `read_radar_snapshot()` then returns data.
- **Commit:** `radar-G.3: radar snapshot worker job + cron`

### G.4 — API endpoint + schemas
- **Files:** `backend/app/schemas/domain.py`, `backend/app/api/routes.py`.
- **domain.py — add** `RadarItem(BaseModel)` mirroring the dataclass fields, and
  `RadarResponse(BaseModel)` = `{generated_at: datetime, horizon_hours: int,
  universe_count: int, opportunities: list[RadarItem], threats: list[RadarItem],
  stale: bool}`.
- **routes.py — add:**
  ```python
  @router.get("/radar", response_model=RadarResponse)
  @limiter.limit(DATA_LIMIT)
  def get_radar(request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user)) -> RadarResponse:
      from app.services.radar_service import read_radar_snapshot, compute_radar, cache_radar_snapshot
      # Prefer a per-user (book-aware) snapshot; fall back to global; compute on miss.
      snap = read_radar_snapshot(user_id=user.id) or read_radar_snapshot()
      stale = snap is None
      if snap is None:
          snap = compute_radar(db, user_id=user.id)
          cache_radar_snapshot(snap, user_id=user.id)
      return RadarResponse(stale=stale, **snap)
  ```
  - Note: book-aware per-user snapshot is computed lazily here on first request and cached;
    keep it simple for MVP (no background per-user job).
- **VERIFY:** `curl -s localhost:8000/api/radar -H "Authorization: Bearer <demo token>" | jq`
  returns a valid `RadarResponse`. Add a request test in `backend/tests/`.
- **Commit:** `radar-G.4: GET /api/radar endpoint + schemas`

### G.5 — Frontend types + client fetcher
- **Files:** `frontend/types/domain.ts`, `frontend/lib/api.ts`.
- **domain.ts — add** `RadarItem` and `RadarResponse` TS interfaces matching the Pydantic shapes.
- **api.ts — add** `export async function fetchRadar(): Promise<RadarResponse>` following the
  exact pattern of the existing `fetchMarketsOverview`/`fetchDashboard` (same `apiBaseUrl()`,
  same auth/credentials handling, `cache: "no-store"`).
- **VERIFY:** `tsc --noEmit` passes; `fetchRadar()` typechecks.
- **Commit:** `radar-G.5: radar client types + fetcher`

### G.6 — `radar-panel.tsx`
- **File:** `frontend/components/radar-panel.tsx` (new, client component).
- **What:** two-column board — **Opportunities** (left) and **Threats** (right). Each row is a
  ranked card showing: market code + name, chosen direction badge, the three numbers
  (reuse the existing number formatting / `risk-bubbles` visual language so it feels native),
  `edge_score`, a calibration chip (reuse `calibration-badge.tsx` styling), and a catalyst
  countdown ("catalyst in 14h") when `hours_to_catalyst` is set. The whole card is a
  `next/link` to `/markets/{market_code}` so a click drops the trader straight into the
  workbench for that market.
- **States:** loading skeleton, empty ("All clear — no flagged setups"), and a `stale` ribbon
  when `RadarResponse.stale` is true ("Computing first scan…").
- **VERIFY:** renders against a mocked `RadarResponse` in the dev app; cards link correctly.
- **Commit:** `radar-G.6: radar panel component`

### G.7 — `/radar` route + nav entry
- **Files:** `frontend/app/radar/page.tsx` (new), `frontend/components/app-shell.tsx`.
- **page.tsx:** server component that renders `<RadarPanel />` inside the standard page frame;
  title "Radar". Keep it thin — data fetching lives in the client panel so live updates work.
- **app-shell.tsx:** add `{ href: "/radar", label: "Radar" }` to `navItems` (place it second,
  right after "Markets" — it's the new front door).
- **VERIFY:** `/radar` loads, nav highlights correctly, build passes.
- **Commit:** `radar-G.7: /radar route + nav entry`

### G.8 — Live updates
- **File:** `frontend/components/radar-panel.tsx` (+ reuse `frontend/lib/use-market-stream.ts`).
- **What:** subscribe to the `"ALL"` stream channel; on a `{"type":"radar_updated"}` message,
  refetch `fetchRadar()`. Add an interval poll as the floor (every
  `NEXT_PUBLIC_DATA_REFRESH_MS` or a sane 60s default) so it still updates if the socket drops.
  - Confirm `use-market-stream.ts` can subscribe to `"ALL"`; if it currently assumes a real
    market code, generalise it to accept `"ALL"` (the backend already publishes there).
- **VERIFY:** with the worker running, trigger a `radar_updated` (or run the job manually) and
  watch the panel refetch without a full page reload.
- **Commit:** `radar-G.8: live radar refresh over market stream + poll floor`

### G.9 — Tests + degradation
- **Files:** `backend/tests/test_radar_service.py`, `backend/tests/test_radar_api.py` (new).
- **Cover:**
  - `compute_radar` returns deterministic ranking given fixed seeds (run twice, assert equal).
  - One market raising inside the loop → it is skipped, the rest still rank (monkeypatch
    `assess_risk` to raise for one code).
  - Book-aware: seed an open decision via `create_decision`, assert that market appears in
    `threats` with a book reason.
  - `GET /api/radar` returns 200 with the expected schema; `stale=true` on cold cache.
- **VERIFY:** `cd backend && pytest tests/test_radar_service.py tests/test_radar_api.py -q` green.
- **Commit:** `radar-G.9: radar service + endpoint tests`

### Phase G acceptance gate
Status key: [x] verified by test/static check · [~] verified at component/unit level,
needs a live full-stack run to confirm end-to-end · [ ] not yet.

- [~] `/radar` shows ranked Opportunities and Threats across the 9 markets.
      (Panel + route + endpoint all unit/static-verified; needs a browser run.)
- [x] Cards deep-link into the correct market workbench. (`Link href={/markets/${code}}`.)
- [x] An open blotter position surfaces as a Threat with a readable reason.
      (test_radar_service::test_compute_radar_surfaces_open_book_threat)
- [~] Panel updates live when the worker publishes `radar_updated`.
      (Wiring verified: worker publishes to ALL; hook subscribes to ALL; refetch on
      message. Needs a live socket to confirm the round-trip in a browser.)
- [x] Worker cron maintains the global snapshot; endpoint degrades to on-demand compute.
      (cron registered; endpoint cold-cache path returns stale=true — test_radar_api.)
- [x] All new tests green (5/5). Existing suite: see Progress log when the full run lands.
- **Commit (when live run done):** `radar-G.acceptance: radar live end-to-end`

#### Remaining: live full-stack run (the only [~] items)
Run the stack and open `/radar`:
```
make deploy           # or: backend uvicorn + `arq app.workers.worker.WorkerSettings` + frontend `npm run dev`
```
Confirm: the board renders ranked cards; a card click lands on `/markets/<code>`; with
the worker running, a fresh `radar_snapshot` cron tick flips the panel without reload.

#### FINDING — cold-cache first load is slow without the worker
`GET /api/radar` on a cold cache computes synchronously: `compute_radar` runs the engine
across 9 markets, and the forecast path reaches out to live data providers (EIA/Open-Meteo/
yfinance) with network timeouts. With no Redis/worker pre-warming the cache (e.g. a bare
local backend), the FIRST `/radar` hit can hang for tens of seconds before synthetic
fallbacks kick in. In production this is a non-issue — the `radar_snapshot` cron pre-warms
the global snapshot every refresh cycle, so the endpoint serves from cache. **Possible
follow-up (deferred):** have the cold-cache endpoint return `stale=true` with empty lists
immediately and trigger the compute in the background, instead of blocking the request.

---

## Progress log
Format: `cleanup-0.N / radar-G.N (sha) — one-line result.`

- cleanup-0.1 (uncommitted) — removed 150 accidental " 2" duplicate files; backend source compiles clean (`compileall` EXIT 0).
- cleanup-0.2 (uncommitted) — removed dead `frontend/.next_broken_1780232986/`; KEPT `threex.db`/`test_threex.db` (active dev + test DBs per `backend/.env`).
- cleanup-0.3 (uncommitted) — added `* 2.*` / `* 2` accidental-copy guards to `.gitignore`; verified they ignore throwaway dups.
- cleanup-0.1..0.4 (42af785) — dup files, dead build dir, gitignore guards, superseded chart removed.
- radar-G.1 (9af061e) — cross-market scan + composite ranking service; 2 foundational tests green (engine/calibration stubbed). DBs kept; `price-chart.tsx` was KLineCharts not Recharts (corrected in steps above).
- radar-G.2 (34e8d67) — redis snapshot cache + memory fallback; global/user scopes; verified hermetically (Redis forced down).
- radar-G.3 (bd8b240) — arq `radar_snapshot` cron + `compute_radar_snapshot` job; publishes `radar_updated` on ALL channel; registration verified.
- radar-G.4 (57a3c0f) — `GET /api/radar` + RadarItem/RadarResponse schemas; route registered, schema validates cache-shaped payload. (Note: app import needs env vars DEMO_MODE/EIA_API_KEY/RATE_LIMIT_ENABLED set or it blocks on a socket.)
- fix (11b6e10) — restored price-chart.tsx; cleanup-0.4 had wrongly deleted the live chart impl (broke tsc). See corrected 0.4 above.
- radar-G.5 (195e73d) — RadarItem/RadarResponse TS types + getRadar() in lib/api.ts; `tsc --noEmit` clean.
- radar-G.6 (319547c) — radar-panel.tsx: two-column Opportunities/Threats board, deep-links to workbench; loading/empty/error/stale states; GBP formatting; tsc clean.
- radar-G.7 (8c0c33b) — /radar route (hero + panel) + Radar nav item (2nd). tsc clean. NOTE: full runtime "page loads" check deferred to acceptance gate (needs FE+BE up).
- radar-G.8 (4ddb43d) — live refresh: RadarPanel subscribes to ALL channel, refetches on radar_updated, 60s poll floor; `radar_updated` added to stream type union. tsc clean.
- radar-G.9 (2e47f00) — book-aware threat test + 2 endpoint tests; all 5 radar tests green. (First pytest run warms the ML import ~17min; later runs ~4s.)

## Blockers
Format: `radar-G.N — short description. To unblock: …`

- (none yet)

## Deferred (revisit after Phase G)
- Split `backend/app/api/routes.py` (1,234 lines) into domain routers
  (`risk`, `markets`, `decisions`, `grid`, `portfolio`, `radar`).
- Introduce a lightweight frontend store (Zustand) so workbench + radar + future copilot
  share one live assessment instead of prop-drilling. (Not required for Radar MVP since the
  panel fetches its own data, but it is the prerequisite for the next pillars.)
- Pillars 2–4 from the proposal: Ask-the-Engine (grounded analyst chat), Scenario Studio,
  Receipts & Replay.
