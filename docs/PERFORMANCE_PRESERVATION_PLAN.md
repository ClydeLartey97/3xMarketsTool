# Performance Preservation Plan

## Purpose

I am going to improve the application's performance without weakening the
product or changing how it works for a user. The goal is not to remove
features, reduce the trustworthiness of the risk reads, or make the interface
less capable. The goal is to make the same product feel faster, load less work
up front, avoid repeated accidental calculations, and keep expensive analysis
available exactly where the user expects it.

The non-negotiable rule is:

> Existing workflows must continue to produce the same visible product behavior,
> the same API contracts, and the same decision-grade outputs, unless a change
> is explicitly documented as opt-in, behind a feature flag, or approved as a
> product change.

This means:

- The three headline numbers remain `risk_gbp`, `likely_gbp`, and
  `upside_gbp`.
- Existing API endpoints keep their request and response shapes.
- Existing pages remain reachable at the same routes.
- The market workbench still shows the same sections: identity, hero,
  decision gate, chart, scenarios, path fan, audit, Power BI, context, book,
  calibration, and signals.
- Official risk reads, saved decisions, exports, and audit packs keep using
  decision-grade settings.
- Any faster preview mode must be clearly separated from official numbers.
- Any lazy loading must preserve feature availability. A feature may load when
  it is near the viewport, but it must not disappear or require a new workflow
  unless that change is explicitly accepted.

## Current Performance Risk Areas

I have identified these likely hot spots from the current codebase.

### 1. Market workbench initial load

The market workbench currently fetches `/dashboard/{market_code}` after the
client page mounts.

Relevant files:

- `frontend/components/market-workbench.tsx`
- `frontend/lib/api.ts`
- `backend/app/api/routes.py`
- `backend/app/services/forecast_service.py`

The dashboard endpoint currently does a lot:

- Finds the market.
- Runs or reads the forecast for a 48 hour horizon.
- Refreshes alerts.
- Loads up to 720 recent price points by default.
- Loads recent events.
- Loads recent news.
- Loads alert rows.
- Loads news source metadata.
- Adds latest backtest metrics.
- Adds price provenance metrics.

That is too much work for the first useful paint. The user first needs the
market identity, the trade input, the three numbers, and enough chart data to
orient. Deep evidence can arrive progressively.

### 2. Chart crosshair can trigger risk calculations

The chart calls `onCrosshair`, which updates `cursorTs` in
`MarketWorkbench`. That timestamp is passed into `MarketHero`, then into
`useRiskAssessment`, which can call `/risk-assessment`.

Relevant files:

- `frontend/components/market-workbench.tsx`
- `frontend/components/market-hero.tsx`
- `frontend/components/price-chart.tsx`
- `frontend/lib/use-risk-assessment.ts`

This means a user moving around the chart can cause repeated risk-assessment
requests. That is expensive and can make the app feel unstable. The existing
capability, "risk at the selected chart timestamp", is valuable, so I will not
remove it by default. I will preserve it while reducing duplicate calls.

### 3. Heavy evidence panels run automatically

The path fan and sensitivity ladder each run additional heavy API calls after
a risk read exists.

Relevant files:

- `frontend/components/risk-path-fan.tsx`
- `frontend/components/risk-sensitivity-ladder.tsx`
- `backend/app/api/routes.py`
- `backend/app/services/risk_engine.py`
- `backend/app/services/risk_sensitivity.py`

The current behavior is useful, but it can compete with the first page load.
The correct optimization is not to remove these panels. The correct
optimization is to make them run when the user is close to seeing them, while
keeping their automatic behavior once visible.

### 4. Home page request fan-out

The home page renders market cards. Each `MarketCardLive` fetches prices and
forecasts separately.

Relevant files:

- `frontend/app/page.tsx`
- `frontend/components/market-card-live.tsx`
- `frontend/lib/api.ts`
- `backend/app/api/routes.py`

With nine markets, this can become 18 client requests just to populate the
grid. The visible output can be produced by one overview endpoint.

### 5. Risk engine loads more price history than needed

The risk engine currently loads all price points for the market in ascending
timestamp order. The calculation only uses:

- The latest spot price.
- Recent returns, capped by `_recent_returns(prices, window=168)`.
- The most recent 24 prices for the congestion tightness proxy.

Relevant file:

- `backend/app/services/risk_engine.py`

The query can fetch only the recent rows needed for the same calculation. This
is a behavior-preserving optimization because older rows are not used by the
current math.

### 6. Existing indexes are not composite enough

The models already mark several columns as indexed individually. The hot
queries usually filter by `market_id` and order by timestamp. Composite
indexes are better suited for these access patterns.

Relevant files:

- `backend/app/models/entities.py`
- `backend/alembic/versions/*`

Adding indexes should not change behavior. It should only change query plans.

## Compatibility Contract

Before implementing performance work, I will treat this compatibility contract
as the product's safety rail.

### API compatibility

For existing endpoints:

- I will not remove fields.
- I will not rename fields.
- I will not change field types.
- I will not change required request fields.
- I will not change auth behavior.
- I will not change error semantics except to fix clear bugs.
- I will not silently reduce the quality of official calculations.

If I add new faster endpoints, they will be additive. Existing endpoints stay
available so older frontend code, external scripts, and future integrations do
not break.

### UI compatibility

For existing pages:

- I will not remove sections from the market workbench.
- I will not remove the chart, overlays, path fan, sensitivity ladder, audit
  table, decision diary, position blotter, Power BI panel, news feed, events
  feed, calibration panel, or signal stack.
- I will not add an extra click for a feature that currently appears
  automatically, unless the feature also auto-loads when it becomes visible.
- I will not make the user re-enter information that is currently preserved by
  local storage or open decisions.
- I will not change the meaning of the three bubbles.

### Calculation compatibility

For official calculations:

- I will keep the default official `n_paths` behavior.
- I will not reduce official Monte Carlo path counts for saved decisions,
  exports, audit packs, or final risk reads.
- I will not alter the risk equation to gain speed.
- I will not change the LLM/news coefficients for performance reasons.
- I will not change FX conversion semantics.
- I will not change the basis-trade semantics.
- I will not change the congestion multiplier semantics.

If I introduce previews, I will name and isolate them. A preview must never be
confused with the official read.

## Measurement First

I will not start by guessing. I will create a performance baseline before
changing behavior. Each optimization phase must show before/after measurements.

### Local baseline modes

I will measure both development mode and production-like local mode.

Frontend development:

```bash
cd frontend
npm run dev -- --hostname 127.0.0.1
```

Frontend production-like:

```bash
cd frontend
npm run build
npm run start
```

Backend development:

```bash
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend production-like:

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If the production deployment uses Gunicorn/Uvicorn workers, I will also test
the same worker shape locally or in staging.

### Baseline metrics to collect

I will collect:

- Home page time to first useful paint.
- Market workbench time to first useful paint.
- Market workbench time until chart visible.
- Market workbench time until first official risk read resolves.
- `/markets` latency.
- `/markets/{id}/prices` latency.
- `/markets/{id}/forecast` latency.
- `/dashboard/{market_code}` latency.
- `/risk-assessment` latency.
- `/risk-assessment/paths` latency.
- `/risk-assessment/sensitivity` latency.
- Frontend JS bundle size.
- Number of client API requests on the home page.
- Number of client API requests on first market workbench load.
- Number of risk requests caused by moving around the chart for 10 seconds.
- Database query count for the dashboard endpoint.
- Database query count for the risk endpoint.

### Baseline commands

I will use simple timing first, then add deeper tooling only where needed.

Example API timing:

```bash
curl -w "\nstatus=%{http_code} total=%{time_total}s ttfb=%{time_starttransfer}s\n" \
  -o /tmp/dashboard.json \
  http://127.0.0.1:8000/api/dashboard/GB_POWER
```

Example response size:

```bash
wc -c /tmp/dashboard.json
```

Example frontend build:

```bash
cd frontend
npm run build
```

Example backend test suite:

```bash
cd backend
PYTHONPATH=. pytest
```

Example frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

### Timing instrumentation

I will add temporary or permanent lightweight instrumentation only if it is
useful and low risk.

Preferred backend instrumentation:

- Structured endpoint duration logs.
- Optional `Server-Timing` headers for local/staging.
- SQL query count logging behind an environment flag.
- Per-service timers around forecast, risk simulation, news scoring,
  calibration, and dashboard assembly.

Preferred frontend instrumentation:

- `performance.mark` and `performance.measure` in development builds.
- Console timing behind a development-only flag.
- Browser network waterfall inspection.
- Bundle size output from the Next build.

I will avoid adding heavy analytics dependencies just to debug this.

## Phase 0: Create A Safety Net

This phase must happen before meaningful optimization. The goal is to prove
that later changes preserve behavior.

### 0.1 API schema regression tests

I will add or extend tests that lock down the shape of existing API responses.

Targets:

- `GET /api/markets`
- `GET /api/dashboard/{market_code}`
- `POST /api/risk-assessment`
- `POST /api/risk-assessment/paths`
- `POST /api/risk-assessment/sensitivity`
- `GET /api/markets/{market_id}/risk-calibration`
- `GET /api/decisions`

Acceptance:

- The tests assert that required fields still exist.
- The tests assert type-level expectations.
- The tests do not require exact stochastic values where randomness is
  expected.
- The tests should catch accidental field removal.

### 0.2 Risk-output compatibility tests

Risk results are stochastic because the standard risk endpoint does not always
use a fixed random seed. I will avoid brittle exact-value tests unless a seed
is already available or added only for tests.

I will test:

- Same sign behavior for long and short.
- `risk_gbp` remains non-negative.
- `upside_gbp`, `likely_gbp`, and `risk_gbp` exist and are finite.
- Official responses preserve `n_paths`.
- Coefficients remain present.
- Decision gate remains present.
- Path fan still returns sampled paths for the path endpoint.

Acceptance:

- Performance changes cannot remove the auditability fields.
- Performance changes cannot reduce official `n_paths`.
- Performance changes cannot bypass calibration or decision gate output.

### 0.3 Frontend smoke test checklist

I will keep a manual or automated smoke checklist for these flows:

1. Load the home page.
2. Open a market.
3. See market identity and trade input.
4. See the three risk bubbles.
5. Change position size.
6. Change long/short direction.
7. Change horizon.
8. Confirm the sticky bar appears when scrolling.
9. Confirm the chart renders.
10. Confirm price/forecast data renders.
11. Confirm risk overlay lines still appear.
12. Confirm scenario cards render.
13. Confirm path fan renders when its section is reached.
14. Confirm sensitivity ladder renders when its section is reached.
15. Confirm risk decomposition still shows coefficients.
16. Confirm news and events still render.
17. Confirm decision diary and position blotter still render.
18. Confirm calibration and signal panels still render.
19. Confirm export buttons still work where present.
20. Confirm mobile collapsed sections still open.

Acceptance:

- All existing sections remain available.
- No new required step is introduced for the primary workflow.

## Phase 1: No-Risk Backend Query Improvements

This phase should not change any user-visible behavior.

### 1.1 Add composite indexes

I will add an Alembic migration with composite indexes for the hot access
patterns.

Likely indexes:

```text
price_points(market_id, timestamp)
forecasts(market_id, forecast_for_timestamp)
events(market_id, created_at)
events(article_id)
weather_points(market_id, timestamp)
demand_points(market_id, timestamp)
risk_assessment_logs(market_id, timestamp)
risk_assessment_logs(user_id, market_id, timestamp)
risk_assessment_logs(user_id, is_open, timestamp)
audit_log(created_at)
```

I will verify exact table names from the SQLAlchemy models and existing
migrations before writing the migration.

Rules:

- I will not remove existing indexes in the same change.
- I will make index names explicit and stable.
- I will make the migration reversible.
- I will account for SQLite compatibility in tests.

Acceptance:

- Alembic upgrade succeeds.
- Alembic downgrade succeeds where the project expects downgrades.
- Existing tests still pass.
- Query plans improve for market/timestamp queries.

### 1.2 Limit risk-engine price history reads

Current risk assessment loads all price points for a market, then only uses
recent windows.

I will change the query to fetch the latest bounded window, then reverse it
back into ascending order so the existing helper functions continue to work.

Current behavior used by the calculation:

- `spot = prices[-1]`
- `_recent_returns(prices)` uses the last 168 rows by default.
- Congestion tightness uses `prices[-24:]`.

Planned query shape:

```python
select(PricePoint)
  .where(PricePoint.market_id == market.id)
  .order_by(PricePoint.timestamp.desc())
  .limit(max(240, 168 + 1))
```

Then:

```python
prices = list(reversed(rows))
```

I will choose a limit that is safely larger than the largest current lookback
used in the risk engine. If a future calculation needs more history, it must
increase the named constant instead of returning to unbounded reads.

Acceptance:

- Risk results are equivalent within stochastic tolerance.
- `spot` is unchanged.
- Recent-return sample size is unchanged when the database has enough rows.
- Congestion tightness uses the same most recent 24 rows.
- The risk endpoint does not load multi-year price history.

### 1.3 Avoid repeated market lookups inside a single request

Where a request already has a `Market` object, I will avoid re-querying the
same market unless necessary.

Acceptance:

- Query count decreases.
- No endpoint response changes.

## Phase 2: Preserve Chart Timestamp Risk While Removing Duplicate Calls

This phase must be careful. The chart timestamp behavior appears intentional,
so I will preserve it.

### 2.1 Deduplicate crosshair emissions

The chart should not call `onCrosshair` repeatedly for the same candle
timestamp and same close value.

In `frontend/components/price-chart.tsx`, I will store the last emitted
crosshair key in a ref:

```text
timestamp + close + forecast flag
```

If the next crosshair event has the same key, I will not call the parent.

This preserves the current behavior when the user moves to a different candle,
but stops repeated state updates while the cursor remains within the same
logical point.

Acceptance:

- Moving within the same candle does not cause repeated parent updates.
- Moving to a different candle still updates the selected timestamp.
- Clearing the crosshair still clears the selected timestamp.

### 2.2 Deduplicate risk requests in the hook

In `frontend/lib/use-risk-assessment.ts`, I will keep a small in-memory cache
or last-request key for the active component instance.

The key must include:

- `marketCode`
- `position`
- `direction`
- `horizon`
- `cursorTimestampMs`
- `paused`

If the key is unchanged, the hook must not send another request.

I will also use `AbortController` if the fetch path supports it, or otherwise
keep the current cancellation guard and ensure stale responses cannot overwrite
newer state.

Acceptance:

- The same logical inputs do not cause duplicate risk requests.
- Changing position still recomputes.
- Changing direction still recomputes.
- Changing horizon still recomputes.
- Moving to a different chart timestamp still recomputes.
- Stale responses do not overwrite newer results.

### 2.3 Optional future pin mode, not default

A future product improvement could change hover behavior into "hover to inspect,
click to pin, pinned timestamp recalculates risk." That would likely feel
better. However, because the requirement is identical behavior, I will not make
that the default in this performance pass.

If implemented later, it must be behind a feature flag:

```text
NEXT_PUBLIC_RISK_TIMESTAMP_MODE=hover|pin
```

Default must remain:

```text
hover
```

Acceptance:

- No user-visible timestamp workflow changes in the default configuration.

## Phase 3: Keep Heavy Evidence Automatic, But Make It Visibility-Aware

This phase improves perceived performance without removing the path fan or
sensitivity ladder.

### 3.1 Add a visibility gate component

I will add a small reusable client component or hook, likely:

```text
frontend/lib/use-near-viewport.ts
```

Behavior:

- It observes a container.
- It returns `true` once the container is within a generous root margin,
  for example `800px`.
- Once true, it stays true for that component instance.
- It gracefully returns true when `IntersectionObserver` is unavailable.

This avoids breaking older browsers or tests.

Acceptance:

- Components near the viewport load automatically.
- Components do not run while far below the fold.
- Once a panel has loaded, scrolling away does not wipe it.

### 3.2 Apply visibility gate to path fan

`RiskPathFan` should not request `/risk-assessment/paths` until its section is
near the viewport. The user should not need to click anything on desktop.

Current behavior:

- Once `data` exists and `loading` is false, it runs.

Preserved behavior:

- Once `data` exists, `loading` is false, and the section is near the viewport,
  it runs automatically.

Acceptance:

- The path fan still appears automatically when the user reaches it.
- It does not compete with the initial hero/chart load.
- It still uses the same request payload and official path settings.

### 3.3 Apply visibility gate to sensitivity ladder

`RiskSensitivityLadder` should not request `/risk-assessment/sensitivity` until
its section is near the viewport.

Preserved behavior:

- It still runs automatically when the user reaches the audit section.
- It still uses the same coefficients.
- It still uses the same path count unless a separate preview mode is created.

Acceptance:

- The sensitivity ladder still appears automatically when the user reaches it.
- It does not compete with first paint.
- It still produces the same table structure.

### 3.4 Prevent repeated heavy-panel recomputation

If `data` changes only by object identity but the logical risk input is the
same, the heavy panels should not refetch.

I will derive stable keys for:

Path fan:

```text
market_code
position_gbp
direction
horizon_hours
target_timestamp
n_paths
```

Sensitivity:

```text
market_code
position_gbp
direction
horizon_hours
target_timestamp
n_paths
coefficients_to_perturb
```

Acceptance:

- Same logical risk read does not retrigger the path fan.
- Same logical risk read does not retrigger sensitivity.
- Real user input changes still refresh both after visibility criteria are met.

## Phase 4: Home Page Overview Endpoint

This phase removes the home page request fan-out while preserving the same card
content.

### 4.1 Add a new endpoint

I will add:

```text
GET /api/markets/overview
```

This endpoint will return one row per market with the exact data needed by
`MarketCardLive`:

- Market metadata.
- Latest spot.
- Previous spot.
- Change.
- 24 hour average price.
- First forecast point.
- Spike probability.
- Data status.

It must not replace `/api/markets`, `/api/markets/{id}/prices`, or
`/api/markets/{id}/forecast`. It is additive.

### 4.2 Preserve home card rendering

I will update the home page so each card receives its stats from the batched
overview response instead of fetching its own prices and forecast.

The visible card output must remain the same:

- Flag.
- Market code.
- Market name.
- Region.
- Timezone.
- Spot.
- Change badge.
- Next hour forecast.
- 24 hour average.
- Spike risk.
- Open desk link.

Acceptance:

- Home page network requests decrease.
- Card values match the old per-card method within the same data freshness
  window.
- Existing detail endpoints still work.

### 4.3 Keep a fallback path

If the overview endpoint fails, the UI may fall back to the current per-card
fetch behavior during development. In production, it can show the existing
loading/fallback state.

Acceptance:

- A temporary overview failure does not break navigation to market pages.

## Phase 5: Split Fast Workbench Data From Deep Evidence

This is the biggest structural improvement. It must be done without breaking
existing endpoint contracts.

### 5.1 Keep the existing dashboard endpoint

I will not remove or change the response shape of:

```text
GET /api/dashboard/{market_code}
```

This endpoint can remain the compatibility endpoint. Tests should lock down
its shape.

### 5.2 Add a fast summary endpoint

I will add an additive endpoint:

```text
GET /api/dashboard/{market_code}/summary
```

This endpoint should return only what the first screen and chart need:

- Market metadata.
- Latest forecast or cached forecast.
- Forecast points.
- Recent prices for the chart window.
- Latest price provenance metrics.
- Minimal key metrics needed above the fold.

It should not refresh alerts synchronously.
It should not perform expensive side effects.
It should not include large news source lists unless the first screen needs
them.

### 5.3 Add or reuse evidence endpoints

Deep evidence can come from existing endpoints:

- `GET /api/markets/{market_id}/events`
- `GET /api/markets/{market_id}/news`
- `GET /api/markets/{market_id}/alerts`
- `GET /api/markets/{market_id}/risk-calibration`
- `GET /api/markets/{market_id}/timeseries`
- `GET /api/markets/{market_id}/backtest/latest`

If a needed endpoint is too broad, I will add a new additive endpoint rather
than changing an existing one.

### 5.4 Update frontend load order

The market workbench should load:

1. Market identity from server-rendered `getMarkets`.
2. Trade input and hero immediately.
3. Fast summary endpoint for chart and lightweight context.
4. Official risk assessment from the hero hook.
5. Evidence panels progressively as they approach the viewport.

The final page content must remain the same once all data has loaded.

Acceptance:

- First useful paint improves.
- The chart still renders.
- Evidence still appears.
- Existing dashboard endpoint remains compatible.
- No section is removed.

### 5.5 Alert refresh must move safely

The current dashboard endpoint calls `refresh_alerts_for_market`. Moving this
out of the first-load path is desirable, but it changes when alerts refresh.

I will only move it when one of these is true:

- A background worker refreshes alerts reliably.
- A dedicated refresh call is made after first paint.
- The existing dashboard endpoint remains available for workflows that require
  synchronous refresh.

Acceptance:

- Active alerts do not silently disappear.
- Alert freshness is either maintained or explicitly measured.
- The user-visible panel still displays alerts when available.

## Phase 6: Forecast And Dashboard Caching

Caching must improve performance without making official outputs stale in a
misleading way.

### 6.1 Forecast cache review

There is already an in-process forecast cache in
`backend/app/services/forecast_service.py`.

I will review:

- Whether the cache key includes horizon correctly.
- Whether active forecaster changes invalidate the right entries.
- Whether data refresh invalidates the right market.
- Whether multi-worker deployments need Redis instead of per-process cache.

Acceptance:

- Cached forecasts match current behavior within the configured TTL.
- Refresh invalidation works.
- Multi-worker behavior is documented.

### 6.2 Add dashboard summary cache

The new summary endpoint can be cached for a short TTL, for example 30 to 120
seconds, keyed by:

- Market code.
- Latest price timestamp.
- Latest forecast timestamp.
- Active forecaster.
- Data status.

I will avoid caching user-specific data in shared caches unless the user ID is
part of the key.

Acceptance:

- Repeated market page loads are faster.
- Data freshness metadata remains visible.
- Refresh invalidation clears affected market cache.

### 6.3 Avoid official risk TTL caching at first

I will not start by adding broad TTL caching to `/risk-assessment`, because the
official endpoint is stochastic and audit-sensitive. Caching could make numbers
look more stable than the current semantics.

Instead, I will first implement:

- Frontend duplicate request suppression.
- Inflight request deduplication where safe.
- Backend query optimizations.

If risk caching is later needed, it must be carefully designed.

Potential later risk cache key:

```text
market_code
position_gbp
position_unit
position_mwh
direction
horizon_hours
target_timestamp
hedge_ratio
n_paths
scenario list
basis market
basis direction
active forecaster
llm scorer provider
latest price timestamp
latest forecast timestamp
latest event timestamp
latest news timestamp
fx timestamp/source
congestion sensitivity version
user id if response includes user-specific data
```

Acceptance for any future risk cache:

- Saved decisions and exports are clearly official.
- Cache provenance is auditable.
- Cache invalidation is tied to data changes.
- Tests prove no field disappears.

## Phase 7: Background Work Separation

This phase improves production performance by moving slow refresh work out of
interactive requests.

### 7.1 Identify synchronous side effects

I will identify request paths that trigger background-style work:

- Forecast refresh.
- Alert refresh.
- Calibration fill.
- Backtest lookup or generation.
- Data refresh.

The dashboard endpoint currently refreshes alerts. Forecast calls may run model
work if the forecast cache is cold.

### 7.2 Move refresh work to workers where already planned

The repo already has worker infrastructure direction in the roadmap. I will
use that instead of inventing a separate system.

Targets:

- Periodic market data refresh.
- Forecast refresh.
- Alert refresh.
- Risk calibration maturity fill.
- Backtest report refresh if needed.

Acceptance:

- Interactive requests read prepared data where possible.
- Manual refresh endpoints still exist where they already exist.
- Audit logging remains intact for mutations.
- Worker failures are visible in logs.

### 7.3 Keep compatibility endpoint behavior until worker confidence is high

I will not immediately remove synchronous work from compatibility endpoints if
doing so changes behavior. I will first make the frontend use faster additive
endpoints and keep the old endpoint as a stable fallback.

Acceptance:

- Existing API consumers are not broken.
- The app's main UI gets faster.

## Phase 8: Frontend Bundle And Render Work

The app already lazy-loads many workbench panels. I will tighten this further
without removing features.

### 8.1 Confirm dynamic imports are effective

I will check that these heavy components are not bundled into the first screen
unnecessarily:

- KLineCharts wrapper.
- Power BI report.
- Risk path fan.
- Risk sensitivity ladder.
- Decision diary.
- Position blotter.
- Calibration panel.
- Signal stack.

Acceptance:

- Initial JS bundle decreases or remains bounded.
- Lazy chunks load when needed.
- No hydration errors are introduced.

### 8.2 Keep Power BI lazy

Power BI is useful but heavy. It should never block the core market workbench.

Acceptance:

- Power BI code does not load before the Power BI section is opened or near
  the viewport.
- The Power BI panel still works when reached.

### 8.3 Avoid unnecessary rerenders

I will inspect whether large props cause unnecessary rerenders:

- `riskOverlay`
- `history`
- `forecast`
- `dashboard`
- `risk`

Potential changes:

- Memoize derived arrays.
- Use stable callbacks.
- Avoid setting state when data is unchanged.
- Suppress duplicate crosshair state updates.

Acceptance:

- UI remains visually identical.
- React rerender count decreases in hot interactions.

## Phase 9: Optional Preview Mode, Strictly Separate From Official Mode

This is optional and should not be part of the first behavior-preserving pass
unless explicitly approved.

### 9.1 Why preview mode exists

Interactive typing can feel slow if every keystroke triggers a full official
Monte Carlo. A preview mode could use fewer paths while the user is actively
editing, then automatically settle to the official read.

### 9.2 Required safeguards

If implemented:

- Preview results must be labelled internally and not saved as official.
- The final settled read must use official settings.
- Exports must use official settings.
- Decision diary saves must use official settings.
- Audit packs must use official settings.
- The UI must not imply that preview numbers are final.

### 9.3 Default position

I will not implement preview mode by default in the first performance pass.
The first pass should preserve official behavior exactly and gain speed from
request suppression, query optimization, lazy evidence, batching, and caching
safe data.

## Phase 10: Production Runtime Improvements

These changes improve deployment performance but do not replace application
optimization.

### 10.1 Frontend production mode

Production frontend must run with:

```bash
npm run build
npm run start
```

or the equivalent platform build/start commands.

Acceptance:

- The app is not served with `next dev` in production.
- Static and server chunks are built once.

### 10.2 Backend production mode

Production backend should not run with `--reload`.

If using Uvicorn directly:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If using multiple workers, I will verify database pool settings and cache
behavior first.

Acceptance:

- No reload watcher in production.
- Worker count matches CPU and memory.
- Long-running jobs are not competing with web requests unnecessarily.

### 10.3 Database and Redis

Production should use Postgres for the main database and Redis for shared
worker/cache needs where implemented.

Acceptance:

- Local SQLite remains supported where tests expect it.
- Production uses Postgres.
- Redis-backed features degrade gracefully when Redis is unavailable in local
  development, if that is currently expected.

## Detailed File-Level Plan

### Backend files likely to change

`backend/app/api/routes.py`

- Add `/markets/overview`.
- Add `/dashboard/{market_code}/summary`.
- Keep existing `/dashboard/{market_code}` response compatible.
- Avoid synchronous heavy side effects in new fast endpoints.

`backend/app/services/forecast_service.py`

- Review forecast cache key behavior.
- Add helper for overview forecast reads if needed.
- Keep existing forecast endpoint behavior.

`backend/app/services/risk_engine.py`

- Replace unbounded price history query with bounded recent-history query.
- Keep ascending `prices` list semantics after fetching.
- Avoid changing the risk equation.
- Avoid changing official `n_paths`.

`backend/app/services/market_service.py`

- Potentially add helper for overview data.
- Keep existing market list behavior.

`backend/app/models/entities.py`

- Usually no model change needed for indexes if indexes are migration-only.
- If using SQLAlchemy `Index` objects, make sure migrations remain correct.

`backend/alembic/versions/*`

- Add composite-index migration.
- Keep SQLite compatibility in mind.

`backend/tests/*`

- Add schema compatibility tests.
- Add bounded-history risk test.
- Add overview endpoint test.
- Add dashboard summary endpoint test.

### Frontend files likely to change

`frontend/lib/api.ts`

- Add `getMarketsOverview`.
- Add `getDashboardSummary`.
- Add optional abort support for risk calls if needed.
- Keep existing API functions.

`frontend/app/page.tsx`

- Fetch overview once.
- Render same market cards.

`frontend/components/market-card-live.tsx`

- Accept preloaded stats.
- Keep fallback loading behavior.
- Avoid per-card fetches when overview data is present.

`frontend/components/market-workbench.tsx`

- Use fast summary endpoint for initial chart/dashboard data.
- Keep evidence sections and ordering.
- Avoid unnecessary state updates.

`frontend/components/price-chart.tsx`

- Suppress duplicate crosshair emissions.
- Preserve timestamp risk behavior.

`frontend/lib/use-risk-assessment.ts`

- Add stable request-key dedupe.
- Add abort/cancellation hardening if fetch supports it.

`frontend/lib/use-near-viewport.ts`

- New hook for visibility-aware heavy panels.

`frontend/components/risk-path-fan.tsx`

- Run automatically only when near viewport.
- Preserve output and payload.

`frontend/components/risk-sensitivity-ladder.tsx`

- Run automatically only when near viewport.
- Preserve output and payload.

`frontend/components/power-bi-report.tsx`

- Confirm lazy load behavior.
- Avoid loading Power BI before needed.

## Acceptance Gates By Phase

### Gate A: Baseline complete

Required evidence:

- Local dev baseline recorded.
- Production-like local baseline recorded.
- Home page request count recorded.
- Market workbench request count recorded.
- Risk endpoint latency recorded.
- Dashboard endpoint latency recorded.
- Frontend build size recorded.

### Gate B: Safety tests complete

Required evidence:

- Backend tests pass.
- Frontend lint passes.
- Frontend build passes.
- API schema tests pass.
- Risk compatibility tests pass.

### Gate C: Query/index phase complete

Required evidence:

- Alembic migration applies.
- Risk endpoint no longer loads unbounded price history.
- Risk output remains compatible within stochastic tolerance.
- Query count or query time improves.

### Gate D: Frontend duplicate suppression complete

Required evidence:

- Chart movement over the same candle does not trigger repeated risk requests.
- Moving to another candle still triggers timestamp risk.
- Position/direction/horizon changes still trigger risk.
- No visible workflow change.

### Gate E: Heavy evidence visibility gate complete

Required evidence:

- Initial market load triggers fewer heavy API calls.
- Path fan still loads automatically before or when the user reaches it.
- Sensitivity ladder still loads automatically before or when the user reaches it.
- No new required click is introduced.

### Gate F: Home overview complete

Required evidence:

- Home page request count drops.
- Market cards display the same fields.
- Values match prior method within the same data freshness window.
- Existing per-market endpoints still work.

### Gate G: Summary endpoint complete

Required evidence:

- Market workbench first useful paint improves.
- Existing dashboard endpoint still passes compatibility tests.
- Summary endpoint returns enough data for first screen and chart.
- Evidence panels still fill in progressively.

### Gate H: Final regression complete

Required evidence:

- Backend test suite passes.
- Frontend lint passes.
- Frontend production build passes.
- Manual or automated smoke checklist passes.
- Before/after performance table is updated.
- Any intentional timing changes are documented.

## Performance Budget Targets

These are targets, not promises. They should be refined after baseline
measurement.

### Local production-like target

Home page:

- First useful paint under 1.5 seconds.
- No more than 3 API requests for initial market grid.

Market workbench:

- First useful paint under 2 seconds.
- Trade input visible immediately after route load.
- Chart visible under 3 seconds.
- First official risk read under 3 seconds for normal cases.
- No path fan or sensitivity request before those sections are near viewport.

Risk endpoint:

- P50 under 800 ms if forecast cache is warm.
- P95 under 2.5 seconds if forecast cache is warm.

Dashboard summary:

- P50 under 500 ms if forecast cache is warm.
- P95 under 1.5 seconds if forecast cache is warm.

### Production target

These should be measured on the actual host:

- Home page first useful paint under 1.5 seconds.
- Market workbench first useful paint under 2 seconds.
- Risk endpoint P95 under 2 seconds for standard 5,000 path reads.
- Heavy evidence does not block first interaction.

## Rollback Plan

Every phase should be easy to revert.

### Additive endpoints

If a new endpoint causes trouble:

- Revert frontend usage to the old endpoint.
- Keep the old endpoint untouched.
- Remove the new endpoint only after tests are restored.

### Index migration

If an index migration causes trouble:

- Revert or downgrade the migration.
- Keep code behavior unchanged.
- Re-run tests.

### Frontend lazy loading

If visibility gating causes a panel not to load:

- Disable the gate and return to immediate loading.
- Keep the panel component code unchanged.

### Risk query optimization

If bounded history changes risk behavior unexpectedly:

- Increase the bounded window.
- Add a test that proves the required history length.
- Revert to unbounded only as a temporary emergency fallback.

## What I Will Not Do In The First Pass

I will not:

- Remove the path fan.
- Remove the sensitivity ladder.
- Remove the audit coefficient table.
- Remove the Power BI panel.
- Remove chart timestamp risk capability.
- Reduce official Monte Carlo paths.
- Change the risk equation.
- Change endpoint response shapes.
- Change auth semantics.
- Replace the forecasting model for performance reasons.
- Hide degraded data warnings.
- Make saved decisions use preview calculations.
- Make exports use preview calculations.

## Recommended Implementation Order

This is the safest order.

1. Measure baseline.
2. Add compatibility tests.
3. Add composite indexes.
4. Limit risk-engine price history reads.
5. Suppress duplicate chart crosshair emissions.
6. Suppress duplicate risk hook requests.
7. Add visibility-aware loading for path fan and sensitivity ladder.
8. Add home overview endpoint and switch home cards to it.
9. Add dashboard summary endpoint.
10. Switch market workbench to summary plus progressive evidence.
11. Review and improve forecast/dashboard caching.
12. Move refresh work to workers only after the faster read path is stable.
13. Re-measure.
14. Write before/after results into this document or a follow-up report.

## Final Definition Of Done

This performance project is complete only when:

- The app feels faster in production-like mode.
- Existing user workflows still work.
- Existing endpoint contracts are preserved.
- Official risk reads remain decision-grade.
- Heavy evidence remains available.
- No first-screen workflow is made weaker.
- Tests pass.
- A before/after performance table exists.
- Any future optional behavior changes are behind flags or documented as
  product decisions.

