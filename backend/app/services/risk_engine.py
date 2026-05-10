"""
Risk-assessment engine.

Produces three numbers for a position in a given market:

  - risk        : capital at risk (£), defined as 95% CVaR over the horizon
  - likely      : expected P&L (£), forecast distribution mean × position
  - upside      : 95th-percentile P&L (£), the realistic upside tail

The numbers are conditioned on:
  - quant features: realised volatility, forecast distribution,
                    intra-horizon variance scaling, regime classification
  - LLM features: catalyst severity, directional asymmetry, tail multiplier
                  (see services/llm_scorer.py)

This is the part that's the product's edge: the combination of the
forecast distribution + LLM-conditioned tail modelling means two markets
with the same point forecast can have very different risk reads when one
has loaded news flow and the other doesn't.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Forecast, Market, NewsArticle, PricePoint
from app.services.forecast_service import run_forecast_for_market
from app.services.fx import fx_to_gbp
from app.services.llm_scorer import ScoredArticle, score_news_context
from app.services.risk_simulator import (
    SimConfig,
    empirical_max_drawdown,
    empirical_risk_metrics,
    pnl_from_paths,
    simulate_price_paths,
)


# Standard normal inverse for one-sided 95% (z ≈ 1.6449)
_Z95 = 1.6449
# CVaR multiplier under normality at 95% (φ(z)/(1-α) ≈ 2.0627)
_CVAR95_NORMAL = 2.0627
# CVaR multiplier under Student-t with 5 dof at α=0.95
# E[T | T > t_{0.95}] / σ ≈ 2.73 for t(5)
_CVAR95_T5 = 2.73


def _cvar95_multiplier(tail_multiplier: float) -> float:
    """Blend Gaussian and t(5) CVaR multipliers based on the LLM tail read.

    When the LLM signals a tail-heavy regime (tail_multiplier > 1.2) the
    Gaussian closed-form understates CVaR. We linearly interpolate toward a
    t(5) approximation as the multiplier grows, fully transitioning by 2.0.
    """
    if tail_multiplier <= 1.2:
        return _CVAR95_NORMAL
    weight = min(1.0, (tail_multiplier - 1.2) / 0.8)
    return (1.0 - weight) * _CVAR95_NORMAL + weight * _CVAR95_T5


@dataclass
class ScenarioSpec:
    name: str
    sigma_multiplier: float = 1.0
    drift_shift: float = 0.0
    spot_shock_pct: float = 0.0


@dataclass
class RiskInputs:
    market_code: str
    position_gbp: float
    horizon_hours: int
    target_timestamp: datetime | None  # if set, narrow assessment to that hour
    direction: str  # "long" or "short"
    position_unit: str = "GBP"          # "GBP" (notional) or "MWh"
    position_mwh: float | None = None
    hedge_ratio: float = 1.0
    n_paths: int = 5000
    scenarios: list[ScenarioSpec] | None = None
    random_seed: int | None = None
    coefficient_overrides: dict[str, float] | None = None
    path_sample_size: int | None = None
    # E.3 — cross-zone basis trade. When set, the engine runs paired
    # paths for both markets using the correlation matrix and reports
    # P&L on the price spread.
    basis_against_market_code: str | None = None
    basis_direction: str = "long"


# Canonical scenarios — keyed by name. Each one specifies a multiplicative
# σ shift, an additive log-return drift per hour, and an instantaneous spot
# shock (% of spot at t=0). The risk engine maps these to the simulator.
PRESET_SCENARIOS: dict[str, ScenarioSpec] = {
    "wind_drop_30pct":  ScenarioSpec("wind_drop_30pct",  sigma_multiplier=1.25, drift_shift=+0.0040, spot_shock_pct=+0.04),
    "outage_2gw":       ScenarioSpec("outage_2gw",       sigma_multiplier=1.40, drift_shift=+0.0080, spot_shock_pct=+0.08),
    "heatwave_+5C":     ScenarioSpec("heatwave_+5C",     sigma_multiplier=1.30, drift_shift=+0.0060, spot_shock_pct=+0.05),
    "gas_spike_+50pct": ScenarioSpec("gas_spike_+50pct", sigma_multiplier=1.20, drift_shift=+0.0100, spot_shock_pct=+0.10),
}


def _resolve_scenario(spec: ScenarioSpec) -> ScenarioSpec:
    """If `spec.name` matches a preset, use the preset; else use spec verbatim."""
    return PRESET_SCENARIOS.get(spec.name, spec)


def _recent_returns(prices: list[PricePoint], window: int = 168) -> np.ndarray:
    if len(prices) < 4:
        return np.array([])
    values = np.array([p.price_value for p in prices[-window:]], dtype=float)
    if (values <= 0).any():
        # power prices can technically go negative; fall back to absolute returns
        diffs = np.diff(values)
        ref = np.maximum(np.abs(values[:-1]), 1.0)
        return diffs / ref
    return np.diff(np.log(values))


def _hourly_vol(returns: np.ndarray) -> float:
    if returns.size < 6:
        return 0.06  # fallback, ~6% hourly std typical for power
    # Robust std via MAD-style scaling
    centered = returns - np.median(returns)
    mad = np.median(np.abs(centered))
    sigma = max(float(mad * 1.4826), float(np.std(returns, ddof=0)))
    return max(0.005, min(0.6, sigma))


def _select_forecast(forecasts: list[Forecast], target: datetime | None, horizon_hours: int) -> Forecast | None:
    if not forecasts:
        return None
    if target is None:
        # default to the last point inside the horizon
        bound = min(horizon_hours, len(forecasts)) - 1
        return forecasts[max(0, bound)]
    # find nearest forecast timestamp
    target_utc = target.astimezone(timezone.utc) if target.tzinfo else target.replace(tzinfo=timezone.utc)
    return min(
        forecasts[: max(1, horizon_hours)],
        key=lambda f: abs((_as_utc(f.forecast_for_timestamp) - target_utc).total_seconds()),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_scored_articles(news: list[NewsArticle]) -> list[ScoredArticle]:
    out: list[ScoredArticle] = []
    for article in news[:20]:
        raw = article.raw_json or {}
        published = _as_utc(article.published_at)
        out.append(
            ScoredArticle(
                title=str(raw.get("translated_title") or article.title),
                summary=str(raw.get("translated_summary") or raw.get("summary") or article.body[:280] or ""),
                source=article.source_name,
                published_at=published,
                credibility=float(raw.get("credibility_rating") or 70.0),
            )
        )
    return out


def _recent_market_articles(db: Session, market: Market, limit: int = 20) -> list[NewsArticle]:
    articles = list(
        db.scalars(
            select(NewsArticle)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit * 4)
        ).all()
    )
    if not articles:
        return []

    article_ids = [article.id for article in articles]
    events_by_article = {
        event.article_id: event
        for event in db.scalars(select(Event).where(Event.article_id.in_(article_ids)))
        if event.article_id is not None
    }

    selected: list[NewsArticle] = []
    for article in articles:
        raw = article.raw_json or {}
        event = events_by_article.get(article.id)
        raw_market_code = raw.get("market_code")
        if event and event.market_id == market.id:
            selected.append(article)
        elif event and event.market_id is None and not raw_market_code:
            selected.append(article)
        elif raw_market_code == market.code:
            selected.append(article)
        elif not event and not raw_market_code:
            selected.append(article)
        if len(selected) >= limit:
            break
    return selected


def _events_summary(events: list[Event]) -> list[dict[str, Any]]:
    return [
        {
            "event_type": e.event_type,
            "severity": e.severity,
            "affected_region": e.affected_region,
            "title": e.title,
        }
        for e in events[:10]
    ]


def assess_risk(db: Session, inputs: RiskInputs) -> dict[str, Any]:
    market = db.scalar(select(Market).where(Market.code == inputs.market_code))
    if not market:
        raise ValueError(f"unknown market {inputs.market_code}")

    # 1) Forecast distribution
    forecasts, model_metrics = run_forecast_for_market(
        db, market, horizon_hours=max(inputs.horizon_hours, 24), use_cache=True
    )
    chosen = _select_forecast(forecasts, inputs.target_timestamp, inputs.horizon_hours)
    if not chosen:
        raise ValueError("no forecast available for this market")

    # 2) Realised vol from price history
    prices = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id)
            .order_by(PricePoint.timestamp.asc())
        ).all()
    )
    spot = prices[-1].price_value if prices else chosen.point_estimate
    returns = _recent_returns(prices)
    sigma_h = _hourly_vol(returns)
    sigma_horizon = sigma_h * np.sqrt(max(1.0, inputs.horizon_hours))

    # 3) LLM-conditioned context
    news = _recent_market_articles(db, market)
    events = list(
        db.scalars(
            select(Event)
            .where(Event.market_id == market.id)
            .order_by(Event.created_at.desc())
            .limit(10)
        ).all()
    )
    context = dict(score_news_context(
        market_code=market.code,
        market_name=market.name,
        region=market.region,
        articles=_build_scored_articles(news),
        events_summary=_events_summary(events),
    ))
    overrides = inputs.coefficient_overrides or {}
    for key in ("tail_multiplier", "asymmetry", "catalyst_severity"):
        if key in overrides:
            context[key] = float(overrides[key])

    # 4) Build the price-distribution σ for the horizon
    # Source 1 — model-implied σ from the forecast snapshot.
    point = float(chosen.point_estimate)
    fcst_lower = float(chosen.lower_bound)
    fcst_upper = float(chosen.upper_bound)
    snapshot = chosen.feature_snapshot_json or {}
    snapshot_sigma = snapshot.get("sigma_price")
    if snapshot_sigma is not None:
        sigma_model = float(snapshot_sigma)
    else:
        half_band = max(point - fcst_lower, fcst_upper - point, max(spot * 0.02, 1.0))
        sigma_model = half_band / _Z95

    if spot <= 0:
        spot = max(point, 1.0)

    # Source 2 — realised σ from recent prices, scaled to the horizon.
    sigma_realised_price = sigma_h * np.sqrt(max(1.0, inputs.horizon_hours)) * spot

    # Sample-size-weighted blend, tail multiplier baked into the simulator
    # call below (not into σ here — keeps the units clean).
    n_obs = float(returns.size)
    w_realised = min(1.0, n_obs / 168.0)
    sigma_price_horizon = (1.0 - w_realised) * sigma_model + w_realised * sigma_realised_price

    # Convert horizon-σ in price units → hourly σ in log-return space, which
    # is what the simulator expects.
    sigma_hourly = (sigma_price_horizon / spot) / np.sqrt(max(1.0, inputs.horizon_hours))

    # Drift in log-return space. Forecast point already encodes the model
    # drift; pull (forecast - spot) into a per-hour log return, then add the
    # LLM asymmetry × catalyst nudge.
    horizon_log_return = float(np.log(max(point, 1e-6) / max(spot, 1e-6)))
    drift_hourly_base = horizon_log_return / max(1.0, inputs.horizon_hours)
    asym_drift = 0.05 * sigma_hourly * float(context["asymmetry"]) * float(context["catalyst_severity"])
    drift_hourly = drift_hourly_base + asym_drift
    if "sigma_hourly" in overrides:
        sigma_hourly = max(0.0, float(overrides["sigma_hourly"]))
        sigma_price_horizon = sigma_hourly * np.sqrt(max(1.0, inputs.horizon_hours)) * spot
        asym_drift = 0.05 * sigma_hourly * float(context["asymmetry"]) * float(context["catalyst_severity"])
        drift_hourly = drift_hourly_base + asym_drift
    if "drift_hourly" in overrides:
        drift_hourly = float(overrides["drift_hourly"])

    direction_sign = 1.0 if inputs.direction.lower() == "long" else -1.0

    # Position resolution + FX. Each market's prices are stored in their
    # native currency (Phase 2.1); convert to GBP at the end.
    price_currency = (getattr(prices[-1], "currency", None) if prices else None) or "USD"
    fx = fx_to_gbp(price_currency)
    if "fx_to_gbp" in overrides:
        fx = max(1e-6, float(overrides["fx_to_gbp"]))
    hedge_ratio = max(0.0, float(overrides.get("hedge_ratio", inputs.hedge_ratio)))

    if inputs.position_unit == "MWh":
        position_native = float(inputs.position_mwh or 0.0) * hedge_ratio
    else:
        # Interpret position_gbp as a GBP-denominated notional. Convert into
        # native price-currency notional for the simulator.
        position_native = (inputs.position_gbp / max(fx, 1e-6)) * hedge_ratio

    base_cfg = SimConfig(
        n_paths=int(inputs.n_paths),
        horizon_hours=int(inputs.horizon_hours),
        spot=float(spot),
        sigma_hourly=float(sigma_hourly),
        drift_hourly=float(drift_hourly),
        tail_multiplier=float(context["tail_multiplier"]),
        asymmetry=float(context["asymmetry"]),
        seed=inputs.random_seed,
    )

    base_result = simulate_price_paths(base_cfg)

    # ── E.3 cross-zone basis trade ─────────────────────────────────────────
    # If the caller asked for a basis position, run a correlated MC for the
    # paired market and replace the P&L vector with the spread P&L. We
    # leave `base_result` referring to the primary leg so coefficient and
    # path-fan reporting stays meaningful.
    basis_meta: dict[str, Any] | None = None
    if inputs.basis_against_market_code and inputs.basis_against_market_code != market.code:
        from app.services.correlation import get_correlation_matrix

        paired = db.scalar(select(Market).where(Market.code == inputs.basis_against_market_code))
        if paired is None:
            raise ValueError(f"unknown basis market {inputs.basis_against_market_code}")
        paired_prices = list(
            db.scalars(
                select(PricePoint)
                .where(PricePoint.market_id == paired.id)
                .order_by(PricePoint.timestamp.asc())
            ).all()
        )
        if not paired_prices:
            raise ValueError(f"no prices for basis market {paired.code}")
        paired_spot = float(paired_prices[-1].price_value)
        if paired_spot <= 0:
            paired_spot = max(float(paired_prices[-1].price_value), 1.0)
        paired_returns = _recent_returns(paired_prices)
        paired_sigma_h = _hourly_vol(paired_returns)
        paired_currency = (getattr(paired_prices[-1], "currency", None)) or "USD"
        paired_fx = fx_to_gbp(paired_currency)

        # Correlated shocks: ρ from the cross-market matrix; same n_paths,
        # same horizon, independent seed offset so we don't reuse base draws.
        corr_matrix = get_correlation_matrix(db)
        rho = float(corr_matrix.get(market.code, {}).get(paired.code, 0.0))
        rho = float(np.clip(rho, -0.99, 0.99))
        paired_seed = (inputs.random_seed + 1_000_003) if inputs.random_seed is not None else None
        paired_cfg = SimConfig(
            n_paths=int(inputs.n_paths),
            horizon_hours=int(inputs.horizon_hours),
            spot=float(paired_spot),
            sigma_hourly=float(paired_sigma_h),
            drift_hourly=0.0,  # no forecast → drift-flat is the honest baseline
            tail_multiplier=float(context["tail_multiplier"]),
            asymmetry=0.0,
            seed=paired_seed,
        )
        paired_result = simulate_price_paths(paired_cfg)

        # Apply the correlation: re-mix paired terminal returns with a
        # rho-weighted component of the primary's terminal returns. This
        # is a one-step correlation that preserves marginal distributions
        # well enough for portfolio CVaR purposes — full path-level
        # correlation lands when we have a multivariate driver in C.x.
        primary_term_returns = base_result.returns_terminal
        paired_term_returns = paired_result.returns_terminal
        paired_mu = float(np.mean(paired_term_returns))
        paired_sd = float(np.std(paired_term_returns, ddof=0) or 1e-9)
        primary_mu = float(np.mean(primary_term_returns))
        primary_sd = float(np.std(primary_term_returns, ddof=0) or 1e-9)
        z_primary = (primary_term_returns - primary_mu) / primary_sd
        z_paired = (paired_term_returns - paired_mu) / paired_sd
        z_correlated = rho * z_primary + np.sqrt(max(0.0, 1.0 - rho * rho)) * z_paired
        paired_term_returns_correlated = paired_mu + paired_sd * z_correlated
        paired_terminal = paired_spot * (1.0 + paired_term_returns_correlated)

        # Spread P&L: long spread = primary leg long, paired leg short.
        # `basis_direction` flips this. Position notional is the primary
        # leg's notional; the paired leg matches it in native MWh or
        # GBP-converted notional.
        if inputs.position_unit == "MWh":
            primary_pnl_native = direction_sign * position_native * (
                base_result.terminal_prices - base_result.paths[:, 0]
            )
            paired_position_native = position_native  # 1:1 MWh hedge
            paired_pnl_native = -direction_sign * paired_position_native * (
                paired_terminal - paired_spot
            )
            primary_pnl_gbp = primary_pnl_native * fx
            paired_pnl_gbp = paired_pnl_native * paired_fx
        else:
            primary_pnl_native = direction_sign * position_native * (
                base_result.terminal_prices - base_result.paths[:, 0]
            ) / np.where(base_result.paths[:, 0] == 0, 1.0, base_result.paths[:, 0])
            paired_position_native = (inputs.position_gbp / max(paired_fx, 1e-6)) * hedge_ratio
            paired_pnl_native = -direction_sign * paired_position_native * (
                paired_terminal - paired_spot
            ) / max(paired_spot, 1e-9)
            primary_pnl_gbp = primary_pnl_native * fx
            paired_pnl_gbp = paired_pnl_native * paired_fx

        basis_sign = 1.0 if inputs.basis_direction == "long" else -1.0
        base_pnl_gbp = basis_sign * (primary_pnl_gbp + paired_pnl_gbp)
        base_pnl_native = base_pnl_gbp / max(fx, 1e-9)  # for symmetry; not used downstream

        basis_meta = {
            "primary_market_code": market.code,
            "basis_market_code": paired.code,
            "basis_direction": inputs.basis_direction,
            "correlation_rho": round(rho, 6),
            "primary_spot": round(float(spot), 4),
            "basis_spot": round(float(paired_spot), 4),
            "primary_fx_to_gbp": round(float(fx), 6),
            "basis_fx_to_gbp": round(float(paired_fx), 6),
        }
    else:
        base_pnl_native = pnl_from_paths(
            base_result,
            direction_sign=direction_sign,
            position_native=position_native,
            position_unit=inputs.position_unit,
        )
        base_pnl_gbp = base_pnl_native * fx
    metrics = empirical_risk_metrics(base_pnl_gbp)

    risk_pnl = metrics["cvar95_gbp"]
    likely_pnl = metrics["likely_gbp"]
    upside_pnl = metrics["upside_gbp"]
    var95_pnl = metrics["var95_gbp"]
    prob_loss = metrics["prob_loss"]

    max_dd_gbp = empirical_max_drawdown(
        base_result,
        direction_sign=direction_sign,
        position_native=position_native,
        position_unit=inputs.position_unit,
        fx_to_gbp=fx,
    )

    risk_metric = "cvar_95_t5" if float(context["tail_multiplier"]) > 1.2 else "cvar_95_normal"

    # Scenario sweeps
    scenario_outcomes: list[dict[str, Any]] = []
    for index, spec in enumerate(inputs.scenarios or []):
        scenario = _resolve_scenario(spec)
        shocked_spot = max(1e-6, spot * (1.0 + scenario.spot_shock_pct))
        scen_cfg = SimConfig(
            n_paths=int(inputs.n_paths),
            horizon_hours=int(inputs.horizon_hours),
            spot=shocked_spot,
            sigma_hourly=float(sigma_hourly * scenario.sigma_multiplier),
            drift_hourly=float(drift_hourly + scenario.drift_shift),
            tail_multiplier=float(context["tail_multiplier"]),
            asymmetry=float(context["asymmetry"]),
            seed=(inputs.random_seed + index + 1) if inputs.random_seed is not None else None,
        )
        scen_result = simulate_price_paths(scen_cfg)
        scen_pnl_native = pnl_from_paths(
            scen_result,
            direction_sign=direction_sign,
            position_native=position_native,
            position_unit=inputs.position_unit,
        )
        scen_pnl_gbp = scen_pnl_native * fx
        scen_metrics = empirical_risk_metrics(scen_pnl_gbp)
        scenario_outcomes.append({
            "name": scenario.name,
            "risk_gbp": round(scen_metrics["cvar95_gbp"], 2),
            "likely_gbp": round(scen_metrics["likely_gbp"], 2),
            "upside_gbp": round(scen_metrics["upside_gbp"], 2),
            "prob_loss": round(scen_metrics["prob_loss"], 4),
        })

    # Edge & confidence
    edge = 0.0
    if risk_pnl > 0:
        edge = float(np.clip(likely_pnl / risk_pnl, -2.0, 2.0))
    confidence = float(context["confidence"]) * float(model_metrics.get("directional_accuracy", 0.5) or 0.5)
    confidence = max(0.05, min(0.95, confidence))

    expected_price = float(np.mean(base_result.terminal_prices))
    expected_return_pct = direction_sign * (expected_price - spot) / spot
    sigma_return_pct = sigma_hourly * np.sqrt(max(1.0, inputs.horizon_hours))

    # ── Coefficient breakdown ───────────────────────────────────────────────
    # Every parameter that influenced the three headline numbers, exposed
    # for the UI / audit. Grouped so the frontend can render in sections.
    coeff_items: list[dict[str, Any]] = [
        # Forecast group
        {"key": "spot_price", "label": "Spot price (P₀)", "value": round(spot, 4),
         "unit": price_currency + "/MWh", "group": "forecast",
         "description": "Last observed market price; the simulator's t=0 anchor."},
        {"key": "forecast_price", "label": "Forecast point (P̂_h)", "value": round(point, 4),
         "unit": price_currency + "/MWh", "group": "forecast",
         "description": "Model point estimate at the chosen horizon."},
        {"key": "horizon_log_return", "label": "Forecast-implied log return", "value": round(horizon_log_return, 6),
         "unit": "log-return", "group": "forecast",
         "description": "ln(P̂_h / P₀). Drives base drift."},
        {"key": "drift_hourly_base", "label": "Base hourly drift (μ_base)", "value": round(drift_hourly_base, 6),
         "unit": "log-return/hr", "group": "forecast",
         "description": "Log-return per hour from the forecast point alone."},
        {"key": "sigma_model_price", "label": "Model σ at horizon (price)", "value": round(sigma_model, 4),
         "unit": price_currency + "/MWh", "group": "forecast",
         "description": "Forecast-snapshot σ; widens the model's predictive band."},
        {"key": "model_directional_accuracy", "label": "Model directional accuracy", "value": round(float(model_metrics.get("directional_accuracy", 0.0) or 0.0), 4),
         "unit": "ratio", "group": "forecast",
         "description": "Fraction of test rows whose direction the model called correctly."},
        {"key": "model_mae", "label": "Model MAE", "value": round(float(model_metrics.get("mae", 0.0) or 0.0), 4),
         "unit": price_currency + "/MWh", "group": "forecast",
         "description": "Mean absolute error of the model on the held-out slice."},

        # Realised volatility group
        {"key": "sigma_hourly_realised", "label": "Realised hourly σ", "value": round(float(sigma_h), 6),
         "unit": "log-return/hr", "group": "realised_vol",
         "description": "Robust σ of recent hourly log returns (MAD-based)."},
        {"key": "sigma_realised_horizon_price", "label": "Realised σ at horizon (price)", "value": round(float(sigma_realised_price), 4),
         "unit": price_currency + "/MWh", "group": "realised_vol",
         "description": "Realised hourly σ × √h × spot, in price units."},
        {"key": "n_observed_returns", "label": "# realised returns", "value": float(returns.size),
         "unit": "count", "group": "realised_vol",
         "description": "Sample size used for realised vol; drives the blend weight."},
        {"key": "realised_vol_weight", "label": "Realised-vol blend weight", "value": round(float(w_realised), 4),
         "unit": "ratio", "group": "realised_vol",
         "description": "Weight on realised vs. model σ; saturates at 1.0 with ≥ 168h of returns."},
        {"key": "sigma_price_horizon_blend", "label": "Blended σ at horizon (price)", "value": round(float(sigma_price_horizon), 4),
         "unit": price_currency + "/MWh", "group": "realised_vol",
         "description": "(1−w)·σ_model + w·σ_realised. Pre-tail-multiplier."},

        # LLM context group
        {"key": "tail_multiplier", "label": "LLM tail multiplier", "value": round(float(context["tail_multiplier"]), 4),
         "unit": "x", "group": "llm",
         "description": "News/event-driven volatility inflation. >1.2 swaps CVaR formula to t(5)."},
        {"key": "asymmetry", "label": "LLM asymmetry", "value": round(float(context["asymmetry"]), 4),
         "unit": "[-1,1]", "group": "llm",
         "description": "Directional skew of news flow. +1 = upside-loaded, −1 = downside-loaded."},
        {"key": "catalyst_severity", "label": "LLM catalyst severity", "value": round(float(context["catalyst_severity"]), 4),
         "unit": "[0,1]", "group": "llm",
         "description": "How loaded the news/event flow is with price-moving catalysts."},
        {"key": "asym_drift_per_hour", "label": "Asymmetry-driven drift", "value": round(float(asym_drift), 6),
         "unit": "log-return/hr", "group": "llm",
         "description": "0.05 · σ_h · asymmetry · catalyst_severity. Adds to base drift."},
        {"key": "drift_hourly_total", "label": "Total hourly drift (μ)", "value": round(float(drift_hourly), 6),
         "unit": "log-return/hr", "group": "llm",
         "description": "μ_base + μ_asym. Fed to the simulator."},
        {"key": "cvar_multiplier", "label": "CVaR multiplier", "value": round(float(_cvar95_multiplier(float(context["tail_multiplier"]))), 4),
         "unit": "x", "group": "llm",
         "description": "Closed-form CVaR multiplier (Gaussian → t(5) blend) — informational; the headline CVaR is empirical."},
        {"key": "regime_score", "label": "Regime", "value": {"calm": 0.0, "trending": 0.5, "stressed": 1.0}.get(str(context["regime"]), 0.0),
         "unit": "calm=0, trending=0.5, stressed=1", "group": "llm",
         "description": "LLM read of the current regime."},
        {"key": "llm_confidence", "label": "LLM confidence", "value": round(float(context["confidence"]), 4),
         "unit": "[0,1]", "group": "llm",
         "description": "How confident the scorer is in this read."},

        # FX group
        {"key": "fx_to_gbp", "label": "FX to GBP", "value": round(float(fx), 6),
         "unit": "GBP / " + price_currency, "group": "fx",
         "description": "Conversion from market's native currency to GBP."},
        {"key": "price_currency_native", "label": "Native price currency", "value": 1.0,
         "unit": price_currency, "group": "fx",
         "description": "Currency of the underlying price feed for this market."},

        # Position group
        {"key": "position_gbp", "label": "Position (GBP notional)", "value": round(float(inputs.position_gbp), 2),
         "unit": "GBP", "group": "position",
         "description": "User-supplied GBP notional. Converted to native via FX."},
        {"key": "position_native", "label": "Position (native notional)", "value": round(float(position_native), 4),
         "unit": "MWh" if inputs.position_unit == "MWh" else price_currency,
         "group": "position",
         "description": "What the simulator actually multiplies P&L by."},
        {"key": "hedge_ratio", "label": "Hedge ratio", "value": round(float(hedge_ratio), 4),
         "unit": "ratio", "group": "position",
         "description": "Fraction of nominal position that is unhedged. 1 = fully exposed."},
        {"key": "direction_sign", "label": "Direction sign", "value": float(direction_sign),
         "unit": "+1 long / -1 short", "group": "position",
         "description": "Multiplies P&L. +1 for long, -1 for short."},
        {"key": "horizon_hours", "label": "Horizon", "value": float(inputs.horizon_hours),
         "unit": "hours", "group": "position",
         "description": "How far ahead the simulation runs."},
        {"key": "n_paths", "label": "# Monte Carlo paths", "value": float(inputs.n_paths),
         "unit": "count", "group": "position",
         "description": "Larger = lower sampling error in the three numbers."},

        # Result group — what came out
        {"key": "sigma_hourly_used", "label": "σ hourly fed to simulator", "value": round(float(sigma_hourly), 6),
         "unit": "log-return/hr", "group": "result",
         "description": "Pre-tail-multiplier σ; the simulator inflates by the tail multiplier internally."},
        {"key": "sigma_horizon_pct", "label": "σ over horizon (%)", "value": round(float(sigma_return_pct * 100), 4),
         "unit": "%", "group": "result",
         "description": "σ scaled to the full horizon, expressed as % of spot."},
        {"key": "expected_return_pct", "label": "Expected return (%)", "value": round(float(expected_return_pct * 100), 4),
         "unit": "%", "group": "result",
         "description": "Empirical mean return of the simulated paths."},
        {"key": "prob_loss", "label": "P(loss)", "value": round(float(prob_loss), 4),
         "unit": "[0,1]", "group": "result",
         "description": "Empirical fraction of paths with negative P&L."},
        {"key": "edge_score", "label": "Edge score", "value": round(float(edge), 4),
         "unit": "ratio", "group": "result",
         "description": "likely_gbp / risk_gbp, clamped to [-2, +2]. Reward / risk."},
        {"key": "max_drawdown_gbp", "label": "95th-pct max drawdown", "value": round(float(max_dd_gbp), 2),
         "unit": "GBP", "group": "result",
         "description": "Worst path-running loss at the 95th percentile."},
    ]

    equation = (
        f"P&L = direction × position_native × (P_T − P_0) × FX_to_GBP, "
        f"where P_t follows GBM-with-tails: dlnP = μ dt + σ·tail × dW; "
        f"μ = {drift_hourly:.5f}/hr, σ = {sigma_hourly:.5f}/hr, "
        f"tail = {context['tail_multiplier']:.2f}, n_paths = {inputs.n_paths}."
    )
    coefficients_block = {"items": coeff_items, "equation_summary": equation}

    sampled_paths: list[list[float]] = []
    if inputs.path_sample_size:
        sample_size = min(max(1, int(inputs.path_sample_size)), base_result.paths.shape[0])
        sample_indices = np.linspace(0, base_result.paths.shape[0] - 1, sample_size, dtype=int)
        sampled_paths = np.round(base_result.paths[sample_indices], 4).tolist()

    return {
        "market_code": market.code,
        "market_name": market.name,
        "as_of": datetime.now(timezone.utc),
        "position_gbp": inputs.position_gbp,
        "direction": inputs.direction,
        "horizon_hours": inputs.horizon_hours,
        "target_timestamp": chosen.forecast_for_timestamp,
        "spot_price": round(spot, 2),
        "forecast_price": round(point, 2),
        "expected_price": round(expected_price, 2),
        "sigma_price": round(sigma_price_horizon, 2),
        "sigma_hourly_pct": round(sigma_hourly * 100, 3),
        "expected_return_pct": round(expected_return_pct * 100, 3),
        "sigma_return_pct": round(sigma_return_pct * 100, 3),
        # The three headline numbers — empirical from MC paths
        "risk_gbp": round(risk_pnl, 2),
        "likely_gbp": round(likely_pnl, 2),
        "upside_gbp": round(upside_pnl, 2),
        "risk_metric": risk_metric,
        # Supporting numbers
        "var95_gbp": round(var95_pnl, 2),
        "prob_loss": round(prob_loss, 4),
        "max_drawdown_gbp": round(max_dd_gbp, 2),
        "fx_to_gbp": round(fx, 6),
        "price_currency": price_currency,
        "n_paths": int(inputs.n_paths),
        "edge_score": round(edge, 3),
        "confidence": round(confidence, 3),
        "regime": context["regime"],
        "catalyst_severity": context["catalyst_severity"],
        "asymmetry": context["asymmetry"],
        "tail_multiplier": context["tail_multiplier"],
        "scorer_provider": context.get("provider", "heuristic"),
        "rationale": context["rationale"],
        "scenarios": scenario_outcomes,
        "coefficients": coefficients_block,
        "price_paths": sampled_paths,
        "basis": basis_meta,
    }
