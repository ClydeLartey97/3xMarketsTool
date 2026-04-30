# 3xMarketsTool — Upgrade Plan (MVP → Decision-grade)

This document is the **single source of truth** for upgrading this repo from
MVP to a defensible trading tool. It is written so that Codex (or any other
agent) can pick up at any phase and execute without needing the conversation
that produced it.

Every phase below names exact files, exact line ranges, the bug being fixed,
the new behaviour required, and the acceptance test that proves it.

> **Convention.** When a phase says "do X then Y," do them in order. When it
> says "in parallel," they are independent. When it says "STOP — confirm with
> the user," literally do not start the next phase until the user signs off.

---

## 0. Audit findings (verified against the code at `551dfb5`)

These are concrete bugs and weaknesses I found by reading the code, not
generic advice. Every Phase below points back to one or more of these.

### 0.1 Risk engine

**File:** `backend/app/services/risk_engine.py`

| # | Defect | Location | Severity |
|---|--------|----------|----------|
| A | Realised vol (`sigma_h`, `sigma_horizon`) is computed but **never used** in the risk calculation. The risk numbers depend only on the forecast band + LLM tail multiplier. | `risk_engine.py:182-184` (computed); never referenced after | High |
| B | `sigma_price = half_band / _Z95` treats the forecast `lower/upper` as a 95% band, but the model produces an **80%/90% band** (z=1.28). Downside risk is therefore systematically **understated by ~22%**. | `risk_engine.py:211` reads band as 95%; `forecasting/model.py:107` produces it as `1.28 * residual_std`. | **Critical** |
| C | Closed-form Gaussian only. The brief explicitly asks for distribution-based / Monte Carlo. No path-dependence, no fat tails beyond a sigma multiplier, no portfolio aggregation. | entire `assess_risk` | High |
| D | Drift formula `sigma_price * 0.35 * asymmetry * catalyst_severity` uses an undocumented magic constant. | `risk_engine.py:215` | Medium |
| E | P&L mapping assumes `position_gbp` is GBP-notional and that returns are simple `(P_T - P_0)/P_0`. No notion of MWh, no hedge ratio, no cost basis. A power trader's position is in MWh, not £. | `risk_engine.py:222-226` | High |
| F | `risk_pnl = cvar95_pnl` but `var95_pnl` is also returned. Risk is therefore CVaR but documented in places as "95% downside" — naming is inconsistent. | `risk_engine.py:228-232, 257, 261` | Low (documentation) |
| G | `_Z95 = 1.6449` is the **one-sided 95%** quantile of the standard normal; correct, but pairing it with `_CVAR95_MULT = 2.0627` (φ(z)/(1-α)) is correct *only* under the normal assumption — which the `tail_multiplier` claims to break. So when LLM says "stressed regime, multiplier 2.0," the CVaR formula silently keeps assuming Gaussian tails. | `risk_engine.py:38-40, 229-230` | Medium |

### 0.2 Forecast engine

**File:** `backend/app/services/forecast_service.py`, `backend/app/forecasting/model.py`

| # | Defect | Location | Severity |
|---|--------|----------|----------|
| H | `predict_distribution` uses `1.28 * residual_std` — produces an ~80% band, not 95%. Anything downstream that assumes 95% is wrong. | `forecasting/model.py:107` | **Critical** (couples to defect B) |
| I | The `_composite_signal` blends a model prediction with hand-tuned heuristic terms (`demand_push`, `renewable_drag`, `event_shock`, etc.). The model is then validated as a single black box — there is no test that the heuristic terms actually reduce error vs. the raw GBR. | `forecasting/model.py:47-68, 70-98` | Medium |
| J | Train/test split is a single 80/20 cut (`train[:split], test[split:]`). No rolling-window / walk-forward backtest, no benchmarks (persistence, climatology), no MAE-by-hour breakdown. | `forecasting/model.py:71-98` | High |
| K | The forecast loop in `run_forecast_for_market` blends the model's distribution with a "structural target" using a `blend = min(0.52, 0.2 + step/60)`. So at 24-hour horizon, ~60% of the price is hand-anchored, not modelled. This is a major hidden assumption. | `forecast_service.py:286-301` | High |
| L | `residual_std` is computed once at training time and re-used for *every* horizon step, scaled by `1 + step/18`. No regime-conditional volatility. | `forecasting/model.py:80, 106-107` | Medium |
| M | Forecast cache is in-process (`_forecast_cache: dict`). Multiple workers will produce inconsistent reads. | `forecast_service.py:16-33` | Low (becomes High when we add workers) |

### 0.3 Data layer

**File:** `backend/app/ingestion/real_data.py`

| # | Defect | Location | Severity |
|---|--------|----------|----------|
| N | **Currency unit bug.** ELEXON returns GB prices in **GBP/MWh**. The ingestion multiplies by `gbp_usd` to convert GBP→USD, so the GB market is stored in **USD/MWh**. EU/Nordic markets are stored in EUR/MWh. US markets in USD/MWh. The risk engine uses `position_gbp` and outputs `risk_gbp` with no FX conversion. So GBP "risk" is actually expressed in whichever currency the underlying market happens to be denominated. | `real_data.py:589` | **Critical** |
| O | History fetched from APIs is hard-capped at `days=14` (and the background refresh fetches `days=1`). The DB therefore never holds more than ~14 days. The brief explicitly asks for max-range historical data. | `real_data.py:458, main.py:42` | High |
| P | When EIA / ELEXON / Open-Meteo fail, the pipeline silently falls back to synthetic. There is **no flag in the response** telling the user which series are real and which are synthetic. The `source` column on `PricePoint` records this, but it's not surfaced to the frontend in a way the user sees. | `real_data.py:482-485, 604-605, 612, 622, 628` | High |
| Q | Synthetic price uses `compute_power_price` which is a hand-tuned merit-order model. It produces "plausible" numbers but they are **not real prices** and any risk/forecast trained on synthetic data is meaningless for that market. | `real_data.py:270-354` | High |
| R | `get_gas_price_usd_mmbtu` / `get_ttf_gas_price_eur_mwh` fall back to hard-coded constants (`2.85`, `38.0`) on failure. Same fallback-without-flag problem. | `real_data.py:239, 253` | Medium |

### 0.4 Frontend chart

**File:** `frontend/components/dashboard-experience.tsx`, `frontend/components/price-forecast-chart.tsx`

| # | Defect | Location | Severity |
|---|--------|----------|----------|
| S | Chart history window is capped at 18 / 30 / 48 hours depending on horizon. So even if the DB had months of data, the chart shows ≤ 2 days. | `dashboard-experience.tsx:20-21` | **Critical** |
| T | Backend dashboard endpoint hardcodes `list_recent_prices(db, market.id, 72)` — 72 hours. Even with a chart fix, the API only returns 3 days. | `api/routes.py:206` | **Critical** |
| U | Chart is built on Recharts. Memory note flags KLineCharts v9 as the chosen engine for drawing tools — the migration hasn't happened. | `price-forecast-chart.tsx:1-13` | Medium |
| V | No overlays for demand / wind / solar / events on the chart. | `price-forecast-chart.tsx` (entire) | High |
| W | No multi-market compare view. | n/a | Medium |

### 0.5 Event extraction

**File:** `backend/app/events/extractor.py`

| # | Defect | Location | Severity |
|---|--------|----------|----------|
| X | Pure keyword matching. First match wins (`break` at line 108). Brittle, no confidence calibration, no handling of negation ("**no** outage reported"). | `extractor.py:103-108` | High |
| Y | Capacity regex `(\d{2,5})\s?mw` will match "100 MW gas project announced" as a 100 MW capacity impact even though it's a build announcement, not an outage. | `extractor.py:113` | High |
| Z | No structured event schema beyond a flat row — no zone/node, no duration distribution, no historical analogue lookup. | `models/entities.py` (Event model) | Medium |
| AA | `severity` is set by hand-tuned thresholds (`capacity >= 700 → high`); not learned, not validated. | `extractor.py:116-129` | Medium |

### 0.6 Infrastructure / API

| # | Defect | Location | Severity |
|---|--------|----------|----------|
| AB | SQLite via SQLAlchemy `create_all` — no migrations, no Alembic. | `db/base.py`, `main.py:63` | High (for any deployment) |
| AC | No auth, no rate limiting, no API keys, no per-user data. | `api/routes.py` (entire) | High |
| AD | `BackgroundScheduler` is in-process; if the API process restarts mid-job, the job dies. No retries, no DLQ. | `main.py:67-77` | High |
| AE | No structured logging, no observability, no data-freshness indicator on the API responses. | global | Medium |
| AF | Tests exist but cover only smoke paths (`tests/test_api.py`, `test_forecast_service.py`, `test_event_extractor.py`). No risk-engine tests, no FX/unit tests, no backtest tests. | `backend/tests/` | High |

---

## 1. Phase order

The phases are ordered so each one is **independently shippable** and the next
one builds on it. **Do not skip ahead.** Each phase ends with an acceptance
test you can run.

```
Phase 1  Risk engine — correctness fix              (defects A, B, F, G)
Phase 2  Risk engine — Monte Carlo + units fix       (defects C, E, N, R)
Phase 3  Data layer — extend history + freshness     (defects O, P, Q)
Phase 4  Forecast — backtesting framework + benchmarks (defects J, K, L)
Phase 5  Forecast — calibration + regime conditioning (defects H, I, L)
Phase 6  Chart — extend range + overlays + KLineCharts (defects S, T, U, V, W)
Phase 7  Events — structured schema + LLM classifier  (defects X, Y, Z, AA)
Phase 8  Frontend — multi-panel + alerts + blotter    (UX upgrade)
Phase 9  Infra — Postgres + Alembic + workers         (defects AB, AD, AE)
Phase 10 Infra — auth + rate limiting + observability (defect AC, AE)
```

Phases 1 + 2 are non-negotiable to do first because every other workstream
either depends on a correct risk number (chart annotations, backtest P&L) or
on real, multi-market currency-consistent data.

---

## Phase 1 — Risk engine correctness fix

**Goal.** Make `risk_gbp`, `likely_gbp`, `upside_gbp` mathematically defensible
under the existing Gaussian model — *before* upgrading to Monte Carlo. Fix
the three named defects (A, B, F, G) and add a test suite that pins the math.

### 1.1 Fix defect H first (it cascades into B)

**File:** `backend/app/forecasting/model.py:104-115`

Replace `predict_distribution` with a true 95% band, and expose the residual
std for downstream consumers.

```python
# Standard normal one-sided 95%
_Z95 = 1.6449

def predict_distribution(self, frame: pd.DataFrame) -> pd.DataFrame:
    preds = self.predict(frame)
    horizon_scale = 1.0 + frame["forecast_step"].fillna(0.0).clip(lower=0.0).to_numpy() / 18.0
    sigma = self.residual_std * horizon_scale  # σ at this horizon, in price units
    band = _Z95 * sigma                         # 95% half-width
    return pd.DataFrame(
        {
            "point_estimate": preds,
            "lower_bound": preds - band,
            "upper_bound": preds + band,
            "sigma_price": sigma,                # NEW — exposed σ for risk engine
        },
        index=frame.index,
    )
```

Then in `forecast_service.py:280` (`dist = model.predict_distribution(...)`),
persist `sigma_price` into the `Forecast.feature_snapshot_json` so the risk
engine can read σ directly instead of re-deriving it from the band.

**Acceptance:** add `backend/tests/test_forecast_distribution.py` asserting
that for synthetic residuals with std=10, `band_width / σ ≈ 1.6449` at step=1.

### 1.2 Wire realised vol back in (defect A)

**File:** `backend/app/services/risk_engine.py`

Replace the σ derivation block (lines 207-223). New behaviour: blend
**model-implied σ** (from the forecast residual) with **realised σ** from
recent prices, weighted by sample size.

```python
# Read model-implied σ directly from the persisted forecast snapshot.
snap = chosen.feature_snapshot_json or {}
sigma_model = float(snap.get("sigma_price") or (max(point - fcst_lower, fcst_upper - point) / _Z95))

# Realised σ at the same horizon: hourly σ × √h, mapped back to price units.
sigma_realised_price = sigma_h * np.sqrt(max(1.0, inputs.horizon_hours)) * spot

# Sample-size-weighted blend. With < 24h of data, lean on the model.
n_obs = float(returns.size)
w_realised = min(1.0, n_obs / 168.0)  # full weight at 1 week
sigma_price = (1.0 - w_realised) * sigma_model + w_realised * sigma_realised_price

# Inflate for LLM tail read.
sigma_price *= float(context["tail_multiplier"])
```

### 1.3 Stop pretending CVaR is Gaussian when tails are inflated (defect G)

When `tail_multiplier > 1.2`, switch the CVaR formula to a **Student-t with 5
degrees of freedom** approximation. The CVaR multiplier under t(5) at α=0.95
is approximately `2.73` (vs. `2.0627` under normal).

```python
def _cvar95_multiplier(tail_multiplier: float) -> float:
    # Below 1.2 we trust the Gaussian closed-form. Above, lean toward t(5).
    if tail_multiplier <= 1.2:
        return 2.0627
    # Linear interp 1.2 → 2.0 between Gaussian and t(5)
    weight = min(1.0, (tail_multiplier - 1.2) / 0.8)
    return (1.0 - weight) * 2.0627 + weight * 2.73
```

Then `cvar_mult = _cvar95_multiplier(context["tail_multiplier"])` and use it
where `_CVAR95_MULT` was hardcoded.

### 1.4 Disambiguate `risk_gbp` (defect F)

In the response schema and in code, rename internally so the meaning is
explicit. Keep the public field name `risk_gbp` for backward compat **but**
add a sibling field describing what it is:

```python
"risk_gbp": round(risk_pnl, 2),
"risk_metric": "cvar_95_t5" if context["tail_multiplier"] > 1.2 else "cvar_95_normal",
```

Update `RiskAssessmentResponse` (`backend/app/schemas/domain.py:171`) to
include `risk_metric: str`.

### 1.5 Tests

Create `backend/tests/test_risk_engine.py` with these cases:

1. **Zero-news baseline.** With a flat price series, no events, no news,
   long position 10,000 GBP, 24h horizon, `tail_multiplier=1.0`, `asymmetry=0`,
   `catalyst_severity=0`: assert `likely_gbp ≈ 0`, `risk_gbp` is within ±5%
   of `Z95 * σ_price/spot * 10000` × 2.0627/Z95.
2. **Stressed regime widens risk.** Same inputs but with `tail_multiplier=2.0`:
   `risk_gbp` must be strictly larger than baseline by at least 30%.
3. **Direction sign.** Long vs short with positive expected drift: `likely_gbp`
   flips sign; `risk_gbp` stays non-negative; `upside_gbp` flips sign.
4. **Band → σ round-trip.** Mock a forecast with point=100, lower=90,
   upper=110: assert the implied σ_price is `10/1.6449 ≈ 6.08`.

### 1.6 STOP

After Phase 1 lands, **stop and ask the user to spot-check** a known market
(e.g., GB_POWER) before proceeding to Phase 2.

---

## Phase 2 — Risk engine: Monte Carlo + units fix

**Goal.** Move from closed-form Gaussian to full P&L distributions. Fix the
GBP/USD/EUR currency mess. Introduce explicit position units.

### 2.1 Currency unification (defect N)

This must be done *before* Monte Carlo, otherwise the simulated P&L is in
mixed currencies.

**File:** `backend/app/ingestion/real_data.py`

1. Stop converting ELEXON GBP → USD. Line 589: change `price = float(row["price_gbp_mwh"]) * gbp_usd` to `price = float(row["price_gbp_mwh"])`.
2. Add a `currency` column to `PricePoint` (and to `Forecast`). Migration:
   set `currency = "GBP"` for GB_POWER, `"EUR"` for EPEX_DE/FR + NORDPOOL_SE3,
   `"USD"` for everything else.
3. Update `populate_market_real_data` so every `PricePoint(...)` it creates
   sets `currency` correctly based on `market_code`.

**File:** `backend/app/models/entities.py`

```python
class PricePoint(Base):
    ...
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
```

Same for `Forecast`.

**File:** `backend/app/services/risk_engine.py`

Add an FX step at the boundary: convert the simulated P&L from the market's
native currency to GBP using current FX (cache for 1h).

```python
fx_to_gbp = _fx_rate(price_currency, "GBP")  # 1.0 for GBP, 0.86 for USD, etc.
likely_pnl_gbp = simulated_pnl_native * fx_to_gbp
```

Implement `_fx_rate` using `yfinance` (`USDGBP=X`, `EURGBP=X`) with a 1-hour
in-process cache and a hard-coded fallback. **Log the fallback every time it
fires** so the user knows.

### 2.2 Position units

**File:** `backend/app/schemas/domain.py:163-168`

Add `position_unit: Literal["GBP", "MWh"] = "GBP"` to `RiskAssessmentRequest`,
plus an optional `position_mwh: Optional[float]` and an optional
`hedge_ratio: float = 1.0`.

Risk engine logic:

- If `position_unit == "MWh"`, P&L per simulated path = `position_mwh * (P_T - P_0) * direction_sign * fx_to_gbp`.
- If `position_unit == "GBP"`, fall back to today's behaviour (return-based)
  but with the FX correction applied.

### 2.3 Monte Carlo engine (defect C)

Create `backend/app/services/risk_simulator.py`. Public API:

```python
@dataclass
class SimConfig:
    n_paths: int = 5000
    horizon_hours: int
    spot: float
    sigma_hourly: float          # in log-return space
    drift_hourly: float          # in log-return space
    tail_multiplier: float       # widens σ
    asymmetry: float             # in [-1, 1]
    regime: str                  # 'calm' | 'trending' | 'stressed'
    seed: int | None = None

def simulate_price_paths(cfg: SimConfig) -> np.ndarray:
    """Returns (n_paths, horizon_hours+1) array of prices, path-dependent."""
```

Implementation outline:

1. Generate base shocks `Z ~ Normal(0,1)` of shape `(n_paths, horizon)`.
2. If `tail_multiplier > 1.2`, sample additionally from a Student-t(5)
   distribution and blend: `Z' = (1-w) * Z + w * T5`, where
   `w = clip((tail_multiplier - 1.2) / 0.8, 0, 1)`.
3. Apply asymmetry: `Z' = Z' + asymmetry * 0.25 * something_per_step`.
4. `r_h = drift_hourly + sigma_hourly * tail_multiplier * Z'` per hour.
5. `price_path = spot * exp(cumsum(r_h))`.
6. Return paths.

Then `assess_risk` becomes:

```python
paths = simulate_price_paths(cfg)
P_T = paths[:, -1]                                    # terminal prices
P_0 = paths[:, 0]
if position_unit == "MWh":
    pnl = position_mwh * (P_T - P_0) * direction_sign
else:
    pnl = position_gbp_native * (P_T - P_0) / P_0 * direction_sign
pnl_gbp = pnl * fx_to_gbp

likely_gbp = float(np.mean(pnl_gbp))
upside_gbp = float(np.percentile(pnl_gbp,  95))
var95     = float(-np.percentile(pnl_gbp,  5))
cvar95    = float(-np.mean(pnl_gbp[pnl_gbp <= np.percentile(pnl_gbp, 5)]))
risk_gbp  = max(0.0, cvar95)
```

This is the **real** distribution-based risk number. Empirical, not Gaussian
closed-form.

### 2.4 Path-dependent additions

While we have the paths in memory, expose:

- `prob_loss`: fraction of paths with `pnl_gbp < 0`.
- `prob_target_hit`: optional `target_pnl_gbp` parameter; fraction of paths
  reaching it before horizon.
- `max_drawdown_gbp`: 95th percentile of `min over t of (pnl_t)`.

Add these to `RiskAssessmentResponse`.

### 2.5 Scenario / sensitivity engine

Add an optional `scenarios: list[ScenarioOverride]` block to the request.
Each scenario shifts one input (e.g., `wind_generation_estimate -= 30%`,
`gas_price *= 1.5`) and re-runs the Monte Carlo. Return a `scenarios` list
in the response, each with its own (likely, upside, risk) triple.

For the first cut, support these scenarios deterministically:

- `wind_drop_30pct`
- `outage_2gw`
- `heatwave_+5C`
- `gas_spike_+50pct`

The way this lands: scenarios mutate the **forecast inputs** (which feed
drift / sigma), then re-run sim. We are not re-training the model per
scenario — that's Phase 5.

### 2.6 Tests

`backend/tests/test_risk_simulator.py`:

1. With `sigma=0, drift=0`, all simulated terminal prices == spot and all
   P&L == 0.
2. With known σ and drift, empirical mean/std match analytical to within 5%
   at n=5000.
3. With `tail_multiplier=2.0`, empirical kurtosis > 4 (vs. ~3 for Gaussian).
4. FX path: USD market, position_gbp=10000 long, simulated USD P&L=+1000,
   FX USD/GBP=0.8 → likely_gbp=800.

### 2.7 STOP

Spot-check 3 markets (GB, ERCOT, EPEX_DE) with realistic positions and have
the user confirm the magnitudes look right.

---

## Phase 3 — Data layer: extend history + freshness

**Goal.** Backfill **months** of real history per market. Surface data
provenance to the frontend so the user can see what's real and what's
synthetic.

### 3.1 Backfill historical data

**File:** `backend/app/ingestion/real_data.py`

1. Add a `backfill_market(market_code, lookback_days=365)` function that
   pages through the source APIs in chunks (EIA gives 5000 rows/page; ELEXON
   in 7-day windows; Open-Meteo accepts `past_days` up to 92 — for older,
   use `start_date`/`end_date`).
2. The 14-day cap (`days=14`) is a parameter — the backfill function should
   call EIA per-month to assemble a year. ELEXON allows arbitrary date
   ranges; chunk by 7 days. Open-Meteo: switch to the **archive** endpoint
   `https://archive-api.open-meteo.com/v1/archive` for >92 days back.
3. Add `backend/scripts/backfill.py` that runs `backfill_market` for every
   market and is safe to re-run (uses the existing `existing_ts` dedupe).

### 3.2 Provenance surfacing (defect P)

`PricePoint.source` already records the source. Surface it.

**File:** `backend/app/schemas/domain.py`

Add to `DashboardResponse.key_metrics` two new entries:

```python
"data_freshness_minutes": float,   # age of newest price point, minutes
"synthetic_share_24h": float,      # fraction of last 24h with source="computed-fundamentals" or "synthetic"
```

These get computed in `api/routes.py:get_dashboard` from the price history.

**Frontend.** Add a "Data: 91% real / 9% synthetic — last refresh 4 min ago"
strip at the top of the dashboard. Red border if `synthetic_share_24h > 0.5`.

### 3.3 Remove the merit-order fallback from core paths (defect Q)

`compute_power_price` is fine for the seed/demo dataset, but it should never
be the source for a market the user is actively trading. Concrete change:

1. Add `settings.demo_mode: bool` (default False).
2. When `demo_mode=False` and a market has no real price source after
   ingestion, **mark the market as `data_status="degraded"`** instead of
   silently falling back. The frontend hides the risk numbers for degraded
   markets and shows "Insufficient real data — try refresh."
3. `compute_power_price` keeps existing for demo mode and seed only.

### 3.4 Tests

`backend/tests/test_backfill.py` with httpx mocks to verify chunking +
de-dup. `backend/tests/test_data_freshness.py` for the `synthetic_share_24h`
metric.

### 3.5 STOP

Run backfill against a real EIA key, confirm DB has ≥ 1 year of GB_POWER
hourly prices and at least 90 days for one US market. User confirms.

---

## Phase 4 — Forecast: backtesting framework + benchmarks

**Goal.** No more single-split metrics. Walk-forward backtests, vs. naive
baselines, with hour-of-day and regime breakdowns.

### 4.1 New module: `backend/app/forecasting/backtest.py`

Public API:

```python
@dataclass
class BacktestResult:
    metrics: dict[str, float]               # MAE, RMSE, dir_acc, spike P/R
    metrics_by_hour: dict[int, dict[str, float]]
    metrics_by_regime: dict[str, dict[str, float]]
    calibration: dict[str, float]            # PIT histogram bin shares
    vs_baselines: dict[str, dict[str, float]]  # 'persistence', 'climatology'

def walk_forward_backtest(
    feature_frame: pd.DataFrame,
    *,
    train_window_hours: int = 24 * 60,
    test_window_hours: int = 24 * 7,
    step_hours: int = 24,
    horizon_hours: int = 24,
) -> BacktestResult
```

Implementation: rolling train/test windows. At each step, train on
`[t-train_window, t)`, predict `[t, t+horizon)`, score against actuals,
advance by `step_hours`.

### 4.2 Baselines

In the same file:

- **persistence**: `ŷ_t+h = y_t`.
- **persistence_24h**: `ŷ_t+h = y_t-(24-h)` (yesterday's same hour).
- **climatology**: mean of price at `(hour, day_of_week)` over the training window.

Score these alongside the model. The model **must** beat all three on RMSE
or we have a problem.

### 4.3 Calibration

Compute the PIT (probability integral transform) histogram. For each test
sample, compute `Φ((y_actual - μ_pred) / σ_pred)` and bin into 10 buckets.
A well-calibrated forecaster gives uniform buckets. Report max deviation
from uniform; flag if > 0.05.

### 4.4 Spike precision/recall

- Define spike as: `y > rolling_mean_24 + 2 * rolling_std_24`.
- Predicted spike: `μ_pred > rolling_mean_24 + 1.5 * rolling_std_24`.
- Report precision, recall, F1.

### 4.5 CLI runner

`backend/scripts/backtest.py`: take `--market`, `--lookback-days`, output a
JSON report under `backend/reports/backtest_<market>_<date>.json` and a
short summary printed to stdout.

### 4.6 Tests

`backend/tests/test_backtest.py`: synthetic AR(1) series, assert
walk-forward MAE is finite, persistence baseline matches the analytical
expected MAE within 10%.

### 4.7 STOP

Run backtest on GB_POWER (now that it has 1y of history). User reads the
report. If the model loses to persistence_24h on a market, do **not**
proceed — go back and fix Phase 5 first for that market.

---

## Phase 5 — Forecast: calibration + regime conditioning

**Goal.** Address defects I, K, L. Make the forecast model defensible.

### 5.1 Regime classifier

Add `backend/app/forecasting/regime.py`. A simple HMM or rolling-window
classifier on `rolling_std_24 / rolling_mean_24` and `event_impact`:
`{calm, trending, stressed}`. Persist the regime per timestamp.

### 5.2 Regime-conditional residual std (defect L)

Train per-regime residual std. At forecast time, look up the regime
classification for the input row and use the matching σ. Replace the global
`self.residual_std`.

### 5.3 Strip or test the heuristic blend (defect I)

The hand-tuned `_composite_signal` and the `structural_target` blend in
`forecast_service.py:286-301` need to either prove their worth or go.

Concrete: in the backtest, compare three configurations:

- `model_only` (raw GBR)
- `model + composite_signal` (current `predict()`)
- `model + composite + structural_blend` (current full pipeline)

Keep only the one with the lowest backtest RMSE. Document the choice.

### 5.4 Ensemble option

Add a second model class: `LightGBMQuantileForecastModel` producing
quantile forecasts directly (q=0.05, 0.5, 0.95). Use it as a sanity check
against the GBR + residual-std approach. Average their point predictions
and take their σ as the max of the two implied σs.

### 5.5 Tests

Update `tests/test_forecast_service.py` with: regime classification
stability (same input → same regime), ensemble combine produces median
between sub-models.

### 5.6 STOP — confirm.

---

## Phase 6 — Chart: extend range + overlays + KLineCharts

**Goal.** Defects S, T, U, V, W. Chart becomes a real analysis tool.

### 6.1 Backend: lift the price-history limit (defect T)

**File:** `backend/app/api/routes.py:206`

Change `list_recent_prices(db, market.id, 72)` to read from a new query param
`history_hours: int = Query(default=720, le=8760)`. Default 30 days, max 1 year.

Add a separate endpoint `/markets/{id}/history?from=...&to=...` that returns
arbitrary date ranges (used for the chart's pan/zoom).

### 6.2 Frontend: remove the historyWindow cap (defect S)

**File:** `frontend/components/dashboard-experience.tsx:20-21`

Replace the 18/30/48 cap with a user-selectable range: `1D | 1W | 1M | 3M | 1Y | All`. Default `1M`. Range driver passed down to a new hook
`useMarketHistory(marketCode, range)` that calls the new history endpoint.

### 6.3 Migrate to KLineCharts (defect U)

The memory note already pins KLineCharts v9. Steps:

1. `npm i klinecharts@9` in `frontend/`.
2. New component `frontend/components/kline-price-chart.tsx`. KLineCharts
   uses an imperative `init(container)` API; wrap it in a React component
   with a `ref` and an effect that calls `applyNewData` on data change.
3. Configure the built-in indicators: MA, BOLL, VOL (we need a synthetic
   "volume" series — use **demand_mw** as the lower-pane volume).
4. Built-in drawing tools (trendline, level, range box) from KLineCharts —
   replace the hand-rolled drawing logic in `price-forecast-chart.tsx`.

### 6.4 Overlays (defect V)

KLineCharts supports custom indicators. Add three:

- `wind_share_pct` overlay (line)
- `solar_share_pct` overlay (line)
- `event_markers` (custom shape: triangle at event timestamp, color by
  severity, click → tooltip with event details)

Data: `dashboard.recent_events` already exists; add a parallel
`/markets/{id}/timeseries?series=demand,wind,solar` endpoint that aligns
weather/demand to the price grid.

### 6.5 Multi-market compare (defect W)

New page `/compare`. User picks 2–4 markets. KLineCharts renders them on
shared axis (normalised: indexed to 100 at the range-start). Useful for
spotting basis blowouts.

### 6.6 Tests

Frontend: Playwright/Storybook smoke that the chart loads with 30 days of
data and that drawing a trendline persists across re-render.

Backend: `tests/test_history_endpoint.py` for the date-range filter.

### 6.7 STOP.

---

## Phase 7 — Events: structured schema + LLM classifier

### 7.1 Schema upgrade (defect Z)

**File:** `backend/app/models/entities.py`

Add to `Event`:

- `zone: str | None` (e.g., "ERCOT North", "PJM AEP")
- `node: str | None` (substation/LMP node, when known)
- `magnitude_mw: float | None` (rename `capacity_impact_mw`; deprecate old)
- `duration_hours_estimate: float | None`
- `duration_hours_p10: float | None`, `duration_hours_p90: float | None`
- `analogue_event_ids: list[int] | None` (JSON column) — past events this
  one resembles
- `classifier_version: str` (e.g., "rule-v1", "gemini-v1")

### 7.2 LLM classifier (defects X, Y, AA)

Create `backend/app/events/llm_classifier.py`. Mirrors `llm_scorer.py`:
provider-agnostic, Gemini default, heuristic fallback (the current
extractor becomes the fallback).

Prompt asks Gemini to extract:
`{event_type, severity, magnitude_mw, duration_hours_estimate, zone, confidence, negation_detected}`.

If `negation_detected=true`, drop the event.

### 7.3 Historical analogue matching

Implement `find_analogues(event, db, k=5)` returning the 5 past events with
highest cosine similarity on
`(event_type_one_hot, magnitude_mw, hour_of_day, day_of_week, regime)`.
Surface them in the event detail UI.

### 7.4 Tests

Negation, capacity-mention-but-not-outage, non-event news, full extraction
on a curated 50-article golden set.

### 7.5 STOP.

---

## Phase 8 — Frontend: multi-panel + alerts + blotter

### 8.1 Multi-panel layout

A trading-tool grid using a resizable layout library (e.g.,
`react-resizable-panels`). Default panes: Chart (60%), Risk (20%), News
(20%) on top row; Events (50%), Blotter (50%) on bottom row. User layout
persisted to `localStorage`.

### 8.2 WebSocket push

Backend: `backend/app/api/ws.py` exposing `/ws/markets/{code}` that pushes
`price_tick`, `forecast_revision`, `new_event`, `alert` JSON messages.
Source from a Redis pub/sub (Phase 9 prerequisite — for now, in-process
asyncio queue).

Frontend: `frontend/lib/use-market-stream.ts` hook that connects the WS,
buffers ticks, applies them to KLineCharts via `updateData` for the latest
candle.

### 8.3 Alerts

Already have a `refresh_alerts_for_market` service. Add WS push for new
alerts. Frontend `<AlertsPanel>` already exists — wire the stream.

### 8.4 Trade blotter

New `Position` model: `market_id, opened_at, direction, size_mwh,
entry_price, exit_price?, expected_pnl_at_open_gbp,
realised_pnl_gbp_latest`. Endpoints: `POST /positions`,
`GET /positions?status=open`, `POST /positions/{id}/close`.

Background job (or API hit on each WS tick) recomputes
`realised_pnl_gbp_latest` from the latest spot.

UI: `<TradeBlotter>` with realised vs expected scatter.

### 8.5 STOP.

---

## Phase 9 — Infra: Postgres + Alembic + workers

### 9.1 Postgres

Replace SQLite. Update `backend/app/core/config.py` and `db/session.py` to
read `DATABASE_URL`. Add `psycopg[binary]` to deps.

### 9.2 Alembic

`alembic init backend/alembic`. Generate the initial migration from current
models. **Do not** call `Base.metadata.create_all` in `main.py` anymore.

Codify all the schema additions from Phases 2 / 3 / 7 as proper migrations
(squash if cleaner).

### 9.3 Background workers

Move `_refresh_all_markets` out of `BackgroundScheduler` and into a
dedicated worker process using **arq** (Redis-backed) or **rq**. The API
process only schedules tasks; workers execute them. Retries with
exponential backoff.

### 9.4 Caching

Move `_forecast_cache` and `_score_cache` to Redis. Same TTLs.

### 9.5 STOP.

---

## Phase 10 — Infra: auth + rate limiting + observability

### 10.1 Auth

`fastapi-users` or `Authlib` JWT-based. Endpoints behind `Depends(current_user)`. Per-user `Position` and per-user API tokens.

### 10.2 Rate limiting

`slowapi` middleware. 60 req/min per user on data endpoints; 10 req/min on
risk-assessment.

### 10.3 Logging + observability

Structured JSON logs via `structlog`. OpenTelemetry traces if user wants
them. Health endpoint extended with `db_ok`, `redis_ok`, `last_refresh`.

### 10.4 Data freshness on every response

`X-Data-As-Of: 2026-04-29T12:30:00Z` header on all market endpoints. Pulled
from the latest `PricePoint.timestamp` for that market.

### 10.5 STOP. Ship.

---

## How Codex should pick this up

If a Codex session starts cold:

1. Read this file (`PLAN.md`) end to end.
2. Read the audit section (§0). Confirm each cited file:line still matches.
   If anything has moved, **stop** and re-read the file before editing.
3. Find the most recent commit message starting with `phase-N:` to figure
   out where work left off. Continue at the next sub-step of that phase.
4. Each sub-step ends with an acceptance test. Codex must run the test
   and have it pass before opening a PR for that sub-step.
5. Phase boundaries are STOP gates. Do not cross them without user signoff.

## Commit message convention

```
phase-1.2: wire realised vol back into risk engine
phase-2.3: monte-carlo simulator with t(5) tails
```

This makes resumption from any session trivial.

---

## Out of scope for this plan

- Mobile UI.
- Trade execution / broker integration.
- Real-money risk limits (regulatory).
- Quant-grade derivatives pricing (forwards, options) beyond simple linear
  positions.

These are big enough to deserve their own plans. Park them.
